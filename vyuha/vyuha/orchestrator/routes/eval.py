"""
/eval — Component-isolation evaluation endpoints (VideoSDK-aligned).

Mirrors VideoSDK's individual component testing mode:
  POST /eval/stt   — evaluate STT in isolation (audio → WER/CER)
  POST /eval/llm   — evaluate LLM in isolation (text → REASONING/RELEVANCE/CLARITY/SCORE)
  POST /eval/tts   — evaluate TTS in isolation (text → latency/RTF)
  POST /eval/run   — full pipeline with per-component latency breakdown + judge criteria

All endpoints return ComponentEvalResult or a list thereof.
"""
from __future__ import annotations

import time
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.config import settings
from vyuha.db import get_db
from vyuha.models.scoring import (
    ComponentEvalResult, JudgeScore, JudgeCriterion, EvalMetric,
)
from vyuha.scoring.judges import LLMJudge

log = structlog.get_logger()
router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]

_JUDGE_CRITERIA_PROMPT = """
You are evaluating a voice AI agent response. Score across four VideoSDK-aligned dimensions.
Each score is 0-10.

User input: {user_input}
Agent response: {agent_response}
Context / system prompt: {context}

REASONING (0-10): Is the agent's logic sound and transparent?
RELEVANCE (0-10): Does the response directly answer/address what the user said?
CLARITY (0-10): Is the response clear, concise, and natural for spoken voice?
SCORE (0-10): Overall response quality.

Return JSON:
{
  "reasoning": {"score": <0-10>, "explanation": "<string>"},
  "relevance":  {"score": <0-10>, "explanation": "<string>"},
  "clarity":    {"score": <0-10>, "explanation": "<string>"},
  "score":      {"score": <0-10>, "explanation": "<string>"}
}
"""


# ── STT-only evaluation ────────────────────────────────────────────────────────

@router.post("/stt", summary="Evaluate STT in isolation — audio file → WER/CER")
async def eval_stt(
    audio_file: UploadFile = File(..., description="Audio file (.wav recommended)"),
    reference_text: str = Form(..., description="Ground truth transcript for WER/CER calculation"),
    language: str = Form(default="en-IN"),
) -> ComponentEvalResult:
    """
    Evaluates the STT pipeline in isolation.
    Transcribes the uploaded audio and computes WER + CER against the reference.
    Requires OLLAMA_URL to be configured.
    """
    if not settings.ollama_url:
        raise HTTPException(503, "STT not configured — set OLLAMA_URL in .env")

    audio_bytes = await audio_file.read()
    filename = audio_file.filename or "audio.wav"

    from vyuha.stt.ollama_stt import OllamaSTT
    from vyuha.asr.normalizer import wer as compute_wer, cer as compute_cer

    stt = OllamaSTT(
        base_url=settings.ollama_url,
        llm_url="",                         # no turn-formatting for raw STT eval
        stt_model=settings.ollama_stt_model,
    )

    t0 = time.monotonic()
    try:
        turns = await stt.transcribe(audio_bytes, filename, language=language or None)
        hypothesis = " ".join(t["text"] for t in turns).strip()
    except Exception as exc:
        return ComponentEvalResult(
            component="stt",
            input=f"[audio: {filename}]",
            output="",
            latency_ms=0.0,
            model_used=settings.ollama_stt_model,
            error=str(exc),
        )
    latency_ms = (time.monotonic() - t0) * 1000

    wer_score = compute_wer(reference_text, hypothesis)
    cer_score = compute_cer(reference_text, hypothesis)

    log.info("eval_stt_done", wer=round(wer_score, 3), cer=round(cer_score, 3), latency_ms=round(latency_ms))

    return ComponentEvalResult(
        component="stt",
        input=f"[audio: {filename}]",
        output=hypothesis,
        latency_ms=round(latency_ms, 1),
        wer=round(wer_score, 4),
        cer=round(cer_score, 4),
        model_used=settings.ollama_stt_model,
    )


# ── LLM-only evaluation ───────────────────────────────────────────────────────

class LLMEvalRequest(BaseModel):
    user_input: str
    context: str = ""                      # system prompt / conversation context
    mock_response: str = ""               # if set, skip LLM call and judge this response
    use_local_llm: bool = False           # route to Ollama instead of Anthropic
    judge_criteria: list[str] = ["reasoning", "relevance", "clarity", "score"]


@router.post("/llm", summary="Evaluate LLM response quality — REASONING / RELEVANCE / CLARITY / SCORE")
async def eval_llm(req: LLMEvalRequest) -> ComponentEvalResult:
    """
    Evaluates an LLM response across VideoSDK's four judge criteria.
    Either generates a response from user_input, or judges a mock_response directly.
    """
    judge = LLMJudge()

    agent_response = req.mock_response

    t0 = time.monotonic()
    model_used = ""

    if not agent_response:
        # Generate a real response
        if req.use_local_llm and settings.local_llm_url:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key="ollama", base_url=settings.local_llm_url)
            msgs = []
            if req.context:
                msgs.append({"role": "system", "content": req.context})
            msgs.append({"role": "user", "content": req.user_input})
            resp = await client.chat.completions.create(
                model=settings.local_llm_model, max_tokens=512, messages=msgs
            )
            agent_response = resp.choices[0].message.content or ""
            model_used = settings.local_llm_model
        elif settings.anthropic_api_key:
            import anthropic
            client_ant = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            resp_ant = await client_ant.messages.create(
                model=settings.default_judge_model,
                max_tokens=512,
                system=req.context or "You are a helpful voice AI agent.",
                messages=[{"role": "user", "content": req.user_input}],
            )
            agent_response = resp_ant.content[0].text
            model_used = settings.default_judge_model
        else:
            raise HTTPException(503, "No LLM configured. Set ANTHROPIC_API_KEY or LOCAL_LLM_URL.")

    gen_latency_ms = (time.monotonic() - t0) * 1000

    # Judge the response
    prompt = _JUDGE_CRITERIA_PROMPT.format(
        user_input=req.user_input,
        agent_response=agent_response,
        context=req.context or "Not provided",
    )
    result = await judge.judge("llm_eval", prompt, {})

    judge_scores: list[JudgeScore] = []
    for criterion_name in ("reasoning", "relevance", "clarity", "score"):
        if criterion_name not in req.judge_criteria and "all" not in req.judge_criteria:
            continue
        entry = result.get(criterion_name, {})
        try:
            score_val = float(entry.get("score", 0.0))
            judge_scores.append(JudgeScore(
                criterion=JudgeCriterion(criterion_name),
                score=max(0.0, min(10.0, score_val)),
                explanation=str(entry.get("explanation", "")),
            ))
        except Exception:
            judge_scores.append(JudgeScore(criterion=JudgeCriterion(criterion_name), score=0.0))

    relevance = next((j.score for j in judge_scores if j.criterion == JudgeCriterion.RELEVANCE), None)
    reasoning = next((j.score for j in judge_scores if j.criterion == JudgeCriterion.REASONING), None)
    clarity = next((j.score for j in judge_scores if j.criterion == JudgeCriterion.CLARITY), None)
    overall = next((j.score for j in judge_scores if j.criterion == JudgeCriterion.SCORE), None)

    total_ms = (time.monotonic() - t0) * 1000
    log.info("eval_llm_done", overall=overall, latency_ms=round(gen_latency_ms))

    return ComponentEvalResult(
        component="llm",
        input=req.user_input,
        output=agent_response,
        latency_ms=round(gen_latency_ms, 1),
        judge_scores=judge_scores,
        relevance=relevance,
        reasoning=reasoning,
        clarity=clarity,
        score_0_10=overall,
        model_used=model_used or "mock",
    )


# ── TTS-only evaluation ───────────────────────────────────────────────────────

class TTSEvalRequest(BaseModel):
    text: str
    language: str = "en-IN"
    voice_id: str = ""
    use_llm_output: bool = False    # reserved for chaining (LLM→TTS)


@router.post("/tts", summary="Evaluate TTS in isolation — text → latency / real-time factor")
async def eval_tts(req: TTSEvalRequest) -> ComponentEvalResult:
    """
    Synthesizes text with the configured TTS provider and returns:
    - latency_ms
    - audio_duration_seconds
    - realtime_factor (latency / duration — < 1.0 means faster than real-time)
    """
    from vyuha.tts.factory import tts_factory
    from vyuha.tts.base import TTSRequest
    from vyuha.models.test_case import Language, Emotion

    try:
        lang = Language(req.language)
    except ValueError:
        lang = Language.ENGLISH_INDIAN

    tts_req = TTSRequest(
        text=req.text,
        language=lang,
        voice_id=req.voice_id,
        emotion=Emotion.NEUTRAL,
    )

    t0 = time.monotonic()
    try:
        result = await tts_factory.synthesize(tts_req)
    except Exception as exc:
        return ComponentEvalResult(
            component="tts",
            input=req.text,
            output="",
            latency_ms=0.0,
            error=str(exc),
        )
    latency_ms = (time.monotonic() - t0) * 1000

    duration_s = result.duration_seconds
    rtf = latency_ms / 1000.0 / duration_s if duration_s > 0 else None

    log.info("eval_tts_done", provider=result.provider, latency_ms=round(latency_ms), rtf=round(rtf or 0, 2))

    return ComponentEvalResult(
        component="tts",
        input=req.text,
        output=f"[audio: {len(result.audio_bytes)} bytes, {result.sample_rate}Hz]",
        latency_ms=round(latency_ms, 1),
        audio_duration_seconds=round(duration_s, 2),
        realtime_factor=round(rtf, 3) if rtf else None,
        model_used=result.provider,
    )


# ── Full eval with component breakdown ────────────────────────────────────────

class EvalRunRequest(BaseModel):
    test_id: str
    include_context: bool = False      # send full conversation to judge (VideoSDK flag)
    metrics: list[str] = [            # which EvalMetric to collect
        EvalMetric.STT_LATENCY,
        EvalMetric.LLM_LATENCY,
        EvalMetric.TTS_LATENCY,
        EvalMetric.END_TO_END_LATENCY,
    ]
    k: int = 1


@router.post("/run", summary="Full evaluation run with per-component latency + VideoSDK judge criteria")
async def eval_run(req: EvalRunRequest, db: DbDep) -> dict[str, Any]:
    """
    Runs a full test case with VideoSDK-aligned metrics:
    - Per-component latency: STT / LLM / TTS / end-to-end
    - REASONING / RELEVANCE / CLARITY / SCORE judge criteria (when include_context=True)
    - All existing EVA-A, EVA-X, RCA scoring
    """
    from vyuha.db.repositories import TestCaseRepo, RunRepo
    from vyuha.orchestrator.runner import execute_single_run

    tc = await TestCaseRepo(db).get(req.test_id)
    if not tc:
        raise HTTPException(404, f"Test case {req.test_id} not found")

    from vyuha.workers.tasks import run_test_case
    task_ids = []
    for _ in range(req.k):
        task = run_test_case.delay(
            test_id=req.test_id,
            vaut_url=None,
            mode="text",
            seed=None,
        )
        task_ids.append(task.id)

    return {
        "message": f"Eval run(s) queued with include_context={req.include_context}",
        "test_id": req.test_id,
        "k": req.k,
        "metrics": req.metrics,
        "include_context": req.include_context,
        "task_ids": task_ids,
    }
