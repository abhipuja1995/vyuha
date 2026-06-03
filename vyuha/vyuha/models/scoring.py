from __future__ import annotations

from enum import Enum
from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field

from vyuha.models.rca import RCATag


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"           # infrastructure failure, not agent failure
    INVALID = "INVALID"       # validator rejected conversation


class EvaAScore(BaseModel):
    """Accuracy dimension: did the agent do the right thing?"""
    task_completion: float = Field(ge=0.0, le=1.0)       # deterministic: ground truth match
    faithfulness: float = Field(ge=0.0, le=1.0)          # LLM-as-Judge: no hallucinations
    speech_fidelity: float = Field(ge=0.0, le=1.0)       # LALM-as-Judge: entity audio accuracy

    @property
    def composite(self) -> float:
        return (self.task_completion * 0.5 + self.faithfulness * 0.3 + self.speech_fidelity * 0.2)

    @property
    def passes(self) -> bool:
        from vyuha.config import settings
        return self.composite >= settings.eva_a_pass_threshold


class EvaXScore(BaseModel):
    """Experience dimension: was the conversation natural and usable?"""
    conciseness: float = Field(ge=0.0, le=1.0)           # LLM-as-Judge: brief enough for voice
    conversation_progression: float = Field(ge=0.0, le=1.0)  # LLM-as-Judge: moved forward
    turn_taking: float = Field(ge=0.0, le=1.0)           # LLM-as-Judge: timing quality

    @property
    def composite(self) -> float:
        return (self.conciseness + self.conversation_progression + self.turn_taking) / 3


class TurnResult(BaseModel):
    turn_index: int
    user_utterance: str
    agent_response: str
    agent_response_audio_path: str | None = None
    latency_ms: float
    tool_calls_made: list[str] = Field(default_factory=list)
    tool_calls_expected: list[str] = Field(default_factory=list)


class DiagnosticMetrics(BaseModel):
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    intent_recognition_rate: float = 0.0
    instruction_following_rate: float = 0.0
    repetition_rate: float = 0.0            # occurrences / call
    sentiment_delta: float = 0.0            # drop in 0-1 sentiment score
    named_entity_accuracy: float = 0.0
    tool_call_success_rate: float = 0.0
    hallucination_rate: float = 0.0


class FailureReport(BaseModel):
    eva_a_score: EvaAScore
    eva_x_score: EvaXScore
    failed_criterion: str
    failure_turn_index: int
    failure_excerpt: str                   # transcript snippet at point of failure
    failure_audio_segment_path: str | None = None
    rca_tags: list[RCATag] = Field(default_factory=list)


class RunResult(BaseModel):
    run_id: str
    test_id: str
    started_at: datetime
    completed_at: datetime
    verdict: Verdict
    eva_a: EvaAScore
    eva_x: EvaXScore
    diagnostics: DiagnosticMetrics
    turns: list[TurnResult] = Field(default_factory=list)
    final_db_state: dict[str, Any] = Field(default_factory=dict)
    failure_report: FailureReport | None = None
    judge_model_used: str = ""
    error_message: str | None = None

    @property
    def latency_ms(self) -> float:
        return (self.completed_at - self.started_at).total_seconds() * 1000


class PassKResult(BaseModel):
    """Aggregated result across k runs of the same test case."""
    test_id: str
    k: int
    runs: list[RunResult]

    @property
    def pass_at_k(self) -> float:
        """Probability ≥1 of k runs succeeds (peak performance)."""
        passes = sum(1 for r in self.runs if r.verdict == Verdict.PASS)
        return passes / self.k if self.k > 0 else 0.0

    @property
    def pass_all_k(self) -> float:
        """Probability all k runs succeed (consistency)."""
        return 1.0 if all(r.verdict == Verdict.PASS for r in self.runs) else 0.0

    @property
    def mean_eva_a(self) -> float:
        if not self.runs:
            return 0.0
        return sum(r.eva_a.composite for r in self.runs) / len(self.runs)

    @property
    def mean_eva_x(self) -> float:
        if not self.runs:
            return 0.0
        return sum(r.eva_x.composite for r in self.runs) / len(self.runs)
