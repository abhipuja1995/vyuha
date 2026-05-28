from __future__ import annotations

import httpx
import structlog

from vyuha.config import settings
from vyuha.models.test_case import Language, Emotion
from vyuha.tts.base import TTSProvider, TTSRequest, TTSResult

log = structlog.get_logger()

# Sarvam AI supports these Indian languages natively
_SARVAM_LANGUAGE_MAP: dict[Language, str] = {
    Language.TELUGU: "te-IN",
    Language.TAMIL: "ta-IN",
    Language.HINDI: "hi-IN",
    Language.ODIA: "or-IN",
    Language.KANNADA: "kn-IN",
    Language.MALAYALAM: "ml-IN",
    Language.MARATHI: "mr-IN",
    Language.BENGALI: "bn-IN",
    Language.ENGLISH_INDIAN: "en-IN",
}

_EMOTION_TO_STYLE: dict[Emotion, str] = {
    Emotion.NEUTRAL: "neutral",
    Emotion.FRUSTRATED: "angry",
    Emotion.ANXIOUS: "fearful",
    Emotion.URGENT: "excited",
    Emotion.CALM: "calm",
    Emotion.DISTRESSED: "sad",
}

_BASE_URL = "https://api.sarvam.ai"


class SarvamTTSProvider(TTSProvider):
    """
    Sarvam AI TTS — primary provider for Indian languages.
    Supports all P0/P1 languages and code-switching via mixed-language text.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.sarvam_api_key
        self._client: httpx.AsyncClient | None = None
        if self._api_key:
            self._client = httpx.AsyncClient(
                base_url=_BASE_URL,
                headers={"API-Subscription-Key": self._api_key},
                timeout=30.0,
            )

    @property
    def name(self) -> str:
        return "sarvam"

    def supports_language(self, language: Language) -> bool:
        return bool(self._api_key) and language in _SARVAM_LANGUAGE_MAP

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        lang_code = _SARVAM_LANGUAGE_MAP.get(request.language, "en-IN")
        style = _EMOTION_TO_STYLE.get(request.emotion, "neutral")

        payload = {
            "inputs": [request.text],
            "target_language_code": lang_code,
            "speaker": request.voice_id or "meera",
            "pitch": 0,
            "pace": request.speaking_rate,
            "loudness": 1.0,
            "speech_sample_rate": 16000,
            "enable_preprocessing": True,
            "model": "bulbul:v1",
        }
        if style != "neutral":
            payload["style"] = style

        log.debug("sarvam_tts_request", language=lang_code, chars=len(request.text))

        if not self._client:
            raise RuntimeError("Sarvam API key not configured")
        resp = await self._client.post("/text-to-speech", json=payload)
        resp.raise_for_status()

        data = resp.json()
        # Sarvam returns base64 audio
        import base64
        audio_bytes = base64.b64decode(data["audios"][0])

        return TTSResult(
            audio_bytes=audio_bytes,
            sample_rate=16000,
            duration_seconds=len(audio_bytes) / (16000 * 2),  # 16-bit PCM estimate
            provider=self.name,
        )

    async def synthesize_code_switched(
        self,
        segments: list[tuple[str, Language]],
        emotion: Emotion = Emotion.NEUTRAL,
        speaking_rate: float = 1.0,
        voice_id: str = "",
    ) -> TTSResult:
        """
        Synthesize code-switched speech by stitching segments.
        Each segment is (text, language). Segments are synthesized individually
        and concatenated into a single audio stream.
        """
        import io
        from pydub import AudioSegment

        combined = AudioSegment.empty()
        for text, lang in segments:
            req = TTSRequest(
                text=text,
                language=lang,
                emotion=emotion,
                speaking_rate=speaking_rate,
                voice_id=voice_id,
            )
            result = await self.synthesize(req)
            segment = AudioSegment.from_raw(
                io.BytesIO(result.audio_bytes),
                sample_width=2,
                frame_rate=result.sample_rate,
                channels=1,
            )
            combined += segment

        audio_bytes = combined.raw_data
        return TTSResult(
            audio_bytes=audio_bytes,
            sample_rate=16000,
            duration_seconds=len(combined) / 1000.0,
            provider=self.name,
        )

    async def list_voices(self, language: Language) -> list[dict]:
        # Sarvam has a fixed set of voices per language
        lang_code = _SARVAM_LANGUAGE_MAP.get(language, "en-IN")
        resp = await self._client.get(f"/text-to-speech/voices?language={lang_code}")
        if resp.status_code == 200:
            return resp.json().get("voices", [])
        return []

    async def aclose(self) -> None:
        await self._client.aclose()
