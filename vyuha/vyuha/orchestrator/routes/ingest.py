from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.config import settings
from vyuha.db import TestCaseRepo, get_db
from vyuha.ingestion.models import FailedCallRecord, FailureSignal
from vyuha.ingestion.pipeline import IngestionPipeline

log = structlog.get_logger()
router = APIRouter()
pipeline = IngestionPipeline()

DbDep = Annotated[AsyncSession, Depends(get_db)]

_ALLOWED_AUDIO = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".webm"}


class IngestCallRequest(BaseModel):
    call_id: str
    agent_id: str
    started_at: datetime
    ended_at: datetime
    transcript: list[dict[str, str]]
    tool_call_trace: list[dict[str, Any]] = []
    sentiment_scores: list[float] = []
    language_detected: str = "en-IN"
    task_completed: bool = False
    audio_path: str | None = None
    metadata: dict[str, Any] = {}


def _ingestion_result_to_response(ingestion_result, test_case) -> dict[str, Any]:
    """Shared serialiser for both preview and save responses."""
    return {
        "ingested": True,
        "call_id": ingestion_result.call_id,
        "test_case_id": ingestion_result.generated_test_case_id,
        "failure_signals": [s.value for s in ingestion_result.failure_signals_detected],
        "confidence": ingestion_result.ingestion_confidence,
        "persona": ingestion_result.extracted_persona.model_dump(),
        "test_case": test_case.model_dump(mode="json"),   # full preview payload
    }


@router.post("/call/preview")
async def preview_ingest_call(req: IngestCallRequest) -> dict[str, Any]:
    """
    Run the full ingestion pipeline and return the generated test case for review —
    WITHOUT saving to the database. The client can call POST /test-cases/ to save
    after the user confirms.
    """
    record = FailedCallRecord(**req.model_dump())
    result = await pipeline.ingest(record)
    if result is None:
        return {
            "ingested": False,
            "reason": "No failure signals detected — call does not meet ingestion threshold",
        }
    ingestion_result, test_case = result
    return _ingestion_result_to_response(ingestion_result, test_case)


@router.post("/call")
async def ingest_call(req: IngestCallRequest, db: DbDep) -> dict[str, Any]:
    record = FailedCallRecord(**req.model_dump())
    result = await pipeline.ingest(record)

    if result is None:
        return {
            "ingested": False,
            "reason": "No failure signals detected — call does not meet ingestion threshold",
        }

    ingestion_result, test_case = result
    await TestCaseRepo(db).save(test_case)

    return {
        "ingested": True,
        "call_id": ingestion_result.call_id,
        "test_case_id": ingestion_result.generated_test_case_id,
        "failure_signals": [s.value for s in ingestion_result.failure_signals_detected],
        "confidence": ingestion_result.ingestion_confidence,
        "persona": ingestion_result.extracted_persona.model_dump(),
    }


@router.post("/webhook/twilio")
async def twilio_webhook(request: Request, db: DbDep) -> dict[str, Any]:
    """
    Twilio StatusCallback webhook — receives completed call data.
    Converts to FailedCallRecord and runs ingestion if call failed.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "")
    call_status = form.get("CallStatus", "")
    call_duration = int(form.get("CallDuration", 0))

    if call_status not in ("no-answer", "busy", "failed", "canceled"):
        return {"ingested": False, "reason": f"Call status '{call_status}' is not a failure"}

    now = datetime.now(timezone.utc)
    record = FailedCallRecord(
        call_id=call_sid,
        agent_id=str(form.get("To", "unknown")),
        started_at=now,
        ended_at=now,
        transcript=[],
        task_completed=False,
        failure_signals=[FailureSignal.ABANDONMENT],
        language_detected=str(form.get("caller_language", "en-IN")),
        metadata={"twilio_status": call_status, "duration_s": call_duration},
    )

    result = await pipeline.ingest(record)
    if result is None:
        return {"ingested": False}

    ingestion_result, test_case = result
    await TestCaseRepo(db).save(test_case)
    return {"ingested": True, "test_case_id": ingestion_result.generated_test_case_id}


@router.post(
    "/transcribe",
    summary="Transcribe a call recording via local Ollama (Whisper + LLM formatting)",
)
async def transcribe_recording(
    audio_file: UploadFile = File(..., description="Call recording to transcribe"),
    language: str = Form(default="", description="Language hint (e.g. hi, te, ta, en-IN). Forces Whisper to use the correct script."),
) -> dict[str, Any]:
    """
    Calls the local Ollama instance to:
      1. Transcribe audio → raw text (Whisper)
      2. Format into [{role, text}] turns (LLM)

    Requires ``OLLAMA_URL`` to be set (e.g. ``http://localhost:11434`` for local,
    or an ngrok/cloudflare tunnel URL when the API runs on Railway).
    """
    if not settings.ollama_url:
        raise HTTPException(
            503,
            "Ollama not configured. Set the OLLAMA_URL environment variable "
            "(e.g. http://localhost:11434 for local, or a tunnel URL for Railway).",
        )

    ext = Path(audio_file.filename or "audio.wav").suffix.lower()
    if ext not in _ALLOWED_AUDIO:
        raise HTTPException(400, f"Unsupported format '{ext}'.")

    audio_bytes = await audio_file.read()
    filename = audio_file.filename or f"audio{ext}"

    from vyuha.stt.ollama_stt import OllamaSTT

    stt = OllamaSTT(
        base_url=settings.ollama_url,
        llm_url=settings.ollama_llm_url,
        stt_model=settings.ollama_stt_model,
        llm_model=settings.ollama_llm_model,
    )

    try:
        transcript = await stt.transcribe(audio_bytes, filename, language=language or None)
    except Exception as exc:
        log.error("ollama_transcription_failed", error=str(exc))
        raise HTTPException(502, f"Transcription failed: {exc}") from exc

    return {"transcript": transcript, "turns": len(transcript)}


async def _process_upload(
    audio_file: UploadFile,
    call_id: str,
    agent_id: str,
    language_detected: str,
    task_completed: bool,
    transcript_json: str,
    auto_transcribe: bool,
    save: bool,
    db: AsyncSession | None,
) -> dict[str, Any]:
    """Shared logic for /upload and /upload/preview."""
    ext = Path(audio_file.filename or "call.wav").suffix.lower()
    if ext not in _ALLOWED_AUDIO:
        raise HTTPException(400, f"Unsupported format '{ext}'. Accepted: {sorted(_ALLOWED_AUDIO)}")

    try:
        transcript: list[dict[str, str]] = json.loads(transcript_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"transcript_json is not valid JSON: {exc}") from exc

    audio_bytes = await audio_file.read()
    effective_call_id = call_id or f"UPLOAD-{uuid.uuid4().hex[:8].upper()}"

    # Save audio file
    storage = Path(settings.audio_storage_path) / "calls"
    storage.mkdir(parents=True, exist_ok=True)
    audio_path = storage / f"{effective_call_id}{ext}"
    audio_path.write_bytes(audio_bytes)

    # Auto-transcribe via Ollama/Whisper if no transcript provided
    stt_used = False
    stt_error: str | None = None
    if not transcript and auto_transcribe and settings.ollama_url:
        try:
            from vyuha.stt.ollama_stt import OllamaSTT
            stt = OllamaSTT(
                base_url=settings.ollama_url,
                llm_url=settings.ollama_llm_url,
                stt_model=settings.ollama_stt_model,
                llm_model=settings.ollama_llm_model,
            )
            transcript = await stt.transcribe(audio_bytes, audio_file.filename or f"audio{ext}", language=language_detected or None)
            stt_used = True
            log.info("ollama_stt_auto_transcribed", call_id=effective_call_id, turns=len(transcript))
        except Exception as exc:
            stt_error = str(exc)
            log.warning("ollama_stt_auto_transcribe_failed", call_id=effective_call_id, error=stt_error)

    if not transcript:
        reason = "Audio saved."
        if stt_error:
            reason += f" Whisper transcription failed: {stt_error}"
        else:
            reason += " Add a transcript and re-submit to generate a test case."
        return {
            "ingested": False,
            "call_id": effective_call_id,
            "audio_path": str(audio_path),
            "reason": reason,
            "stt_attempted": auto_transcribe and bool(settings.ollama_url),
        }

    now = datetime.now(timezone.utc)
    record = FailedCallRecord(
        call_id=effective_call_id,
        agent_id=agent_id,
        started_at=now,
        ended_at=now,
        transcript=transcript,
        audio_path=str(audio_path),
        language_detected=language_detected,
        task_completed=task_completed,
        failure_signals=[],
        metadata={"source": "manual_upload", "original_filename": audio_file.filename,
                  **({"stt": "whisper"} if stt_used else {})},
    )

    result = await pipeline.ingest(record)
    if result is None:
        return {
            "ingested": False,
            "call_id": effective_call_id,
            "audio_path": str(audio_path),
            "reason": "No failure signals detected — call does not meet ingestion threshold.",
            "transcript_turns": len(transcript),
        }

    ingestion_result, test_case = result
    test_case.linked_production_call = effective_call_id

    if save and db is not None:
        await TestCaseRepo(db).save(test_case)

    return {
        **_ingestion_result_to_response(ingestion_result, test_case),
        "audio_path": str(audio_path),
        "saved": save,
        **({"stt": "whisper"} if stt_used else {}),
    }


@router.post("/upload/preview", summary="Process a call recording and preview the generated test case without saving")
async def preview_upload_recording(
    audio_file: UploadFile = File(...),
    call_id: str = Form(default=""),
    agent_id: str = Form(default="unknown-agent"),
    language_detected: str = Form(default="en-IN"),
    task_completed: bool = Form(default=False),
    transcript_json: str = Form(default="[]"),
    auto_transcribe: bool = Form(default=True),
) -> dict[str, Any]:
    """Process audio → STT → pipeline → return test case preview WITHOUT saving to DB."""
    return await _process_upload(
        audio_file=audio_file, call_id=call_id, agent_id=agent_id,
        language_detected=language_detected, task_completed=task_completed,
        transcript_json=transcript_json, auto_transcribe=auto_transcribe,
        save=False, db=None,
    )


@router.post("/upload", summary="Upload a call recording and optionally ingest it as a test case")
async def upload_call_recording(
    db: DbDep,
    audio_file: UploadFile = File(..., description="Call recording (WAV, MP3, OGG, FLAC, M4A, AAC, WebM)"),
    call_id: str = Form(default=""),
    agent_id: str = Form(default="unknown-agent"),
    language_detected: str = Form(default="en-IN"),
    task_completed: bool = Form(default=False),
    transcript_json: str = Form(
        default="[]",
        description="JSON array of {role, text} turns. Leave empty to auto-transcribe via Ollama (if configured).",
    ),
    auto_transcribe: bool = Form(
        default=True,
        description="If true and transcript is empty, attempt Ollama STT automatically.",
    ),
) -> dict[str, Any]:
    return await _process_upload(
        audio_file=audio_file, call_id=call_id, agent_id=agent_id,
        language_detected=language_detected, task_completed=task_completed,
        transcript_json=transcript_json, auto_transcribe=auto_transcribe,
        save=True, db=db,
    )
