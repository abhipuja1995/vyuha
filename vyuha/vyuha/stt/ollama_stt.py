"""
Ollama-backed Speech-to-Text.

Two-step pipeline:
  1. Whisper transcription  → raw text (via Ollama's OpenAI-compatible
                               /v1/audio/transcriptions endpoint)
  2. LLM formatting         → structured [{role, text}] transcript
                               (via Ollama's /api/generate endpoint)
     If the LLM model is not configured the raw text is returned as a
     single {"role": "user", "text": "..."} turn.
"""

from __future__ import annotations

import json
import re
import structlog

import httpx

log = structlog.get_logger()

_FORMAT_PROMPT = """\
You are processing a recorded call-centre conversation.
Below is a raw automatic transcription (no speaker labels).

Your task: split the text into conversational turns and assign each turn
the role "agent" or "user".
- The agent (IVR / human agent) always speaks first.
- Identify speaker changes from context: greetings, questions, responses.
- Keep each turn's text verbatim — do not paraphrase.
- Output ONLY a valid JSON array, no explanation, no markdown fences.

Format:
[
  {{"role": "agent", "text": "..."}},
  {{"role": "user",  "text": "..."}}
]

Raw transcript:
{raw}

JSON array:"""


class OllamaSTT:
    """
    Args:
        base_url:  STT server URL (exposes /v1/audio/transcriptions), e.g. local_whisper_server.
        llm_url:   Ollama LLM URL for turn-formatting (exposes /api/generate).
                   Pass ``""`` to skip formatting and return raw text as a single turn.
        stt_model: Model name passed to the STT server.
        llm_model: Ollama model name for turn formatting (e.g. ``llama3.2``).
    """

    def __init__(
        self,
        base_url: str,
        llm_url: str = "",
        stt_model: str = "whisper",
        llm_model: str = "llama3.2",
    ) -> None:
        self._base = base_url.rstrip("/")
        self._llm_base = llm_url.rstrip("/") if llm_url else ""
        self._stt_model = stt_model
        self._llm_model = llm_model

    # ── public ──────────────────────────────────────────────────────────────

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language: str | None = None,
    ) -> list[dict[str, str]]:
        """Return a list of ``{role, text}`` dicts."""
        raw_text = await self._whisper(audio_bytes, filename, language=language)
        log.info("ollama_stt_raw", chars=len(raw_text))

        if self._llm_base and self._llm_model:
            try:
                turns = await self._format(raw_text)
                log.info("ollama_stt_formatted", turns=len(turns))
                return turns
            except Exception as exc:
                log.warning("ollama_stt_format_failed_fallback", error=str(exc))

        # Fallback: single user turn
        return [{"role": "user", "text": raw_text.strip()}]

    # ── private ─────────────────────────────────────────────────────────────

    async def _whisper(self, audio_bytes: bytes, filename: str, language: str | None = None) -> str:
        """Call Ollama's OpenAI-compatible audio transcription endpoint."""
        # Map Vyuha language codes → Whisper language codes (strip region suffix)
        whisper_lang = _to_whisper_lang(language) if language else None
        data: dict = {"model": self._stt_model}
        if whisper_lang:
            data["language"] = whisper_lang
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{self._base}/v1/audio/transcriptions",
                files={"file": (filename, audio_bytes, _mime(filename))},
                data=data,
            )
        if not resp.is_success:
            raise RuntimeError(
                f"Ollama Whisper error {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json().get("text", "")

    async def _format(self, raw_text: str) -> list[dict[str, str]]:
        """Ask the local LLM to label turns as agent / user."""
        prompt = _FORMAT_PROMPT.format(raw=raw_text)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._llm_base}/api/generate",
                json={"model": self._llm_model, "prompt": prompt, "stream": False},
            )
        if not resp.is_success:
            raise RuntimeError(
                f"Ollama LLM error {resp.status_code}: {resp.text[:300]}"
            )
        response_text = resp.json().get("response", "")

        # Extract the JSON array from the response (model may add prose around it)
        match = re.search(r"\[.*?\]", response_text, re.DOTALL)
        if not match:
            raise ValueError("LLM did not return a JSON array")
        turns: list[dict[str, str]] = json.loads(match.group())
        # Validate shape
        for t in turns:
            if "role" not in t or "text" not in t:
                raise ValueError("Unexpected turn shape from LLM")
        return turns


def _to_whisper_lang(lang: str) -> str:
    """Convert Vyuha language codes to Whisper-compatible ISO 639-1 codes."""
    # Strip region suffix: "en-IN" → "en"
    base = lang.split("-")[0].lower()
    # Whisper uses the same codes as ISO 639-1, so most pass through directly.
    # Special cases only:
    _overrides: dict[str, str] = {}
    return _overrides.get(base, base)


def _mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
        "webm": "audio/webm",
    }.get(ext, "audio/wav")
