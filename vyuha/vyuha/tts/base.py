from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from vyuha.models.test_case import Language, Emotion


@dataclass
class TTSRequest:
    text: str
    language: Language
    voice_id: str = ""
    emotion: Emotion = Emotion.NEUTRAL
    speaking_rate: float = 1.0
    seed: int | None = None               # deterministic output for regression tests


@dataclass
class TTSResult:
    audio_bytes: bytes
    sample_rate: int
    duration_seconds: float
    provider: str


class TTSProvider(ABC):
    """Abstract TTS provider. Implement for each vendor."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def supports_language(self, language: Language) -> bool: ...

    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResult: ...

    @abstractmethod
    async def list_voices(self, language: Language) -> list[dict]: ...
