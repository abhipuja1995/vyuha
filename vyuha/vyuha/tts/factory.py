from __future__ import annotations

import structlog

from vyuha.models.test_case import Language
from vyuha.tts.base import TTSProvider, TTSRequest, TTSResult
from vyuha.tts.sarvam import SarvamTTSProvider
from vyuha.tts.azure import AzureTTSProvider
from vyuha.tts.local import LocalTTSProvider

log = structlog.get_logger()


class TTSFactory:
    """
    Selects TTS provider in priority order: Local → Sarvam → Azure.
    Falls back automatically on provider error or missing configuration.
    """

    def __init__(self) -> None:
        self._local = LocalTTSProvider()
        self._sarvam = SarvamTTSProvider()
        self._azure = AzureTTSProvider()
        # ordered preference: Local (if configured) → Sarvam → Azure
        self._providers: list[TTSProvider] = [self._local, self._sarvam, self._azure]

    def _select_provider(self, language: Language) -> list[TTSProvider]:
        """Return providers that support the language, in preference order."""
        return [p for p in self._providers if p.supports_language(language)]

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        candidates = self._select_provider(request.language)
        if not candidates:
            raise ValueError(f"No TTS provider supports language: {request.language}")

        last_error: Exception | None = None
        for provider in candidates:
            try:
                result = await provider.synthesize(request)
                if provider.name != candidates[0].name:
                    log.warning("tts_fallback_used", provider=provider.name, language=request.language)
                return result
            except Exception as exc:
                log.warning("tts_provider_failed", provider=provider.name, error=str(exc))
                last_error = exc

        raise RuntimeError(f"All TTS providers failed for {request.language}") from last_error

    async def list_voices(self, language: Language) -> list[dict]:
        for provider in self._select_provider(language):
            try:
                return await provider.list_voices(language)
            except Exception:
                continue
        return []


# Singleton
tts_factory = TTSFactory()
