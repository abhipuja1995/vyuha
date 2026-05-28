from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FailureSignal(str, Enum):
    REPETITION = "repetition"           # user repeated same info > 2 times
    ABANDONMENT = "abandonment"         # call ended without task completion
    SENTIMENT_DROP = "sentiment_drop"   # sentiment fell below 0.35
    TOOL_ERROR = "tool_error"           # exception or tool call failure in trace


class FailedCallRecord(BaseModel):
    """Raw data from a failed production call."""
    call_id: str
    agent_id: str
    started_at: datetime
    ended_at: datetime
    transcript: list[dict[str, str]]          # [{"role": "user"|"agent", "text": "..."}]
    audio_path: str | None = None             # path to call recording (WAV/MP3)
    tool_call_trace: list[dict[str, Any]] = Field(default_factory=list)
    sentiment_scores: list[float] = Field(default_factory=list)  # per-turn, 0-1
    language_detected: str = "en-IN"          # BCP-47
    task_completed: bool = False
    failure_signals: list[FailureSignal] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractedPersona(BaseModel):
    """Persona inferred from call audio/transcript."""
    language: str
    accent_variant: str
    speaking_rate: float
    noise_profile: str
    emotion: str
    estimated_snr_db: float | None = None
    code_switch_detected: bool = False
    secondary_language: str | None = None


class IngestionResult(BaseModel):
    call_id: str
    failure_signals_detected: list[FailureSignal]
    extracted_persona: ExtractedPersona
    generated_test_case_id: str
    ingestion_confidence: float           # 0-1, how confident we are the test case is valid
