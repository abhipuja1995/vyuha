"""
LocalTTSProvider — wraps any OpenAI-compatible /v1/audio/speech endpoint.

Works with:
  - openedai-speech  (https://github.com/matatonic/openedai-speech)
  - kokoro-fastapi   (https://github.com/remsky/kokoro-FastAPI)
  - Any server that implements POST /v1/audio/speech with
    {"model", "input", "voice", "speed"} and returns raw audio bytes.

Set LOCAL_TTS_URL in .env (e.g. http://host.docker.internal:8880) to enable.
"""
from __future__ import annotations

import structlog
import httpx

from vyuha.config import settings
from vyuha.models.test_case import Language, Emotion
from vyuha.tts.base import TTSProvider, TTSRequest, TTSResult

log = structlog.get_logger()

# These languages may not be supported by all local TTS servers.
# We list all and let the server decide; errors will trigger fallback.
_ALL_LANGUAGES: set[Language] = {
    Language.HINDI, Language.TAMIL, Language.TELUGU, Language.KANNADA,
    Language.MALAYALAM, Language.MARATHI, Language.BENGALI, Language.ODIA,
    Language.ENGLISH_INDIAN, Language.ENGLISH,
}

_EMOTION_TO_SPEED: dict[Emotion, float] = {
    Emotion.NEUTRAL: 1.0,
    Emotion.FRUSTRATED: 1.1,
    Emotion.ANXIOUS: 0.95,
    Emotion.URGENT: 1.2,
    Emotion.CALM: 0.9,
    Emotion.DISTRESSED: 0.85,
}


class LocalTTSProvider(TTSProvider):
    """
    Calls an OpenAI-compatible TTS endpoint at LOCAL_TTS_URL.
    Falls back gracefully when the server is unavailable.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        voice: str | None = None,
    ) -> None:
        self._base_url = (base_url or settings.local_tts_url).rstrip("/")
        self._model = model or settings.local_tts_model
        self._voice = voice or settings.local_tts_voice

    @property
    def name(self) -> str:
        return "local"

    def supports_language(self, language: Language) -> bool:
        return bool(self._base_url) and language in _ALL_LANGUAGES

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self._base_url:
            raise RuntimeError("LOCAL_TTS_URL not configured")

        voice = request.voice_id or self._voice
        speed = _EMOTION_TO_SPEED.get(request.emotion, 1.0) * request.speaking_rate

        payload = {
            "model": self._model,
            "input": request.text,
            "voice": voice,
            "speed": round(speed, 2),
            "response_format": "wav",
        }

        log.debug("local_tts_request", url=self._base_url, chars=len(request.text), voice=voice)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/v1/audio/speech", json=payload)

        if not resp.is_success:
            raise RuntimeError(f"Local TTS error {resp.status_code}: {resp.text[:200]}")

        audio_bytes = resp.content
        sample_rate = 22050  # most local TTS servers default to 22050 Hz
        return TTSResult(
            audio_bytes=audio_bytes,
            sample_rate=sample_rate,
            duration_seconds=len(audio_bytes) / (sample_rate * 2),
            provider=self.name,
        )

    async def list_voices(self, language: Language) -> list[dict]:
        if not self._base_url:
            return []
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/v1/audio/voices")
            if resp.is_success:
                return resp.json().get("voices", [])
        except Exception:
            pass
        return []

    async def health_check(self) -> dict:
        """Ping the local TTS server and return status."""
        if not self._base_url:
            return {"configured": False, "reachable": False, "url": ""}
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._base_url}/v1/models")
            return {
                "configured": True,
                "reachable": resp.is_success,
                "url": self._base_url,
                "status_code": resp.status_code,
            }
        except Exception as exc:
            return {"configured": True, "reachable": False, "url": self._base_url, "error": str(exc)}
