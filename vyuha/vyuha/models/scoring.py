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


class EvalMetric(str, Enum):
    """Per-component latency metrics (mirrors VideoSDK EvalMetric)."""
    STT_LATENCY = "stt_latency"
    LLM_LATENCY = "llm_latency"
    TTS_LATENCY = "tts_latency"
    END_TO_END_LATENCY = "end_to_end_latency"


class JudgeCriterion(str, Enum):
    """LLM judge quality criteria (mirrors VideoSDK LLMAsJudge criteria)."""
    REASONING = "reasoning"     # does the agent explain its response logic?
    RELEVANCE = "relevance"     # does the response actually answer the question?
    CLARITY = "clarity"         # is the response clear and understandable?
    SCORE = "score"             # 0-10 overall quality rating


class JudgeScore(BaseModel):
    """Per-criterion LLM judge score (0-10) with explanation."""
    criterion: JudgeCriterion
    score: float = Field(ge=0.0, le=10.0)
    explanation: str = ""

    @property
    def normalized(self) -> float:
        """Normalized 0-1 for use in composite calculations."""
        return self.score / 10.0


class EvaAScore(BaseModel):
    """Accuracy dimension: did the agent do the right thing?"""
    task_completion: float = Field(ge=0.0, le=1.0)       # deterministic: ground truth match
    faithfulness: float = Field(ge=0.0, le=1.0)          # LLM-as-Judge: no hallucinations
    speech_fidelity: float = Field(ge=0.0, le=1.0)       # LALM-as-Judge: entity audio accuracy
    # VideoSDK-aligned judge criteria (populated when include_context=True)
    relevance: float = Field(ge=0.0, le=1.0, default=0.0)    # response answers the question
    reasoning: float = Field(ge=0.0, le=1.0, default=0.0)    # logic is sound and explained
    clarity: float = Field(ge=0.0, le=1.0, default=0.0)      # understandable for voice
    judge_score_0_10: float = Field(ge=0.0, le=10.0, default=0.0)  # overall 0-10 rating
    judge_details: list[JudgeScore] = Field(default_factory=list)

    @property
    def composite(self) -> float:
        return (self.task_completion * 0.5 + self.faithfulness * 0.3 + self.speech_fidelity * 0.2)

    @property
    def passes(self) -> bool:
        from vyuha.config import settings
        return self.composite >= settings.eva_a_pass_threshold


class EvaXScore(BaseModel):
    """Experience dimension: was the conversation natural and usable?"""
    conciseness: float = Field(ge=0.0, le=1.0)           # brief enough for voice
    conversation_progression: float = Field(ge=0.0, le=1.0)  # moved forward
    turn_taking: float = Field(ge=0.0, le=1.0)           # timing quality

    @property
    def composite(self) -> float:
        return (self.conciseness + self.conversation_progression + self.turn_taking) / 3


class ComponentLatency(BaseModel):
    """Per-component latency breakdown for a single turn (VideoSDK EvalMetric alignment)."""
    stt_latency_ms: float = 0.0      # time to transcribe user audio → text
    llm_latency_ms: float = 0.0      # time for LLM to generate response text
    tts_latency_ms: float = 0.0      # time to synthesize response → audio
    end_to_end_latency_ms: float = 0.0   # total wall-clock turn time

    @classmethod
    def from_total(cls, total_ms: float) -> "ComponentLatency":
        """Estimate breakdown when only total is available."""
        return cls(end_to_end_latency_ms=total_ms)


class TurnResult(BaseModel):
    turn_index: int
    user_utterance: str
    agent_response: str
    agent_response_audio_path: str | None = None
    latency_ms: float                                      # total turn latency (backward compat)
    # Per-component breakdown (VideoSDK-aligned)
    component_latency: ComponentLatency = Field(default_factory=ComponentLatency)
    tool_calls_made: list[str] = Field(default_factory=list)
    tool_calls_expected: list[str] = Field(default_factory=list)


class DiagnosticMetrics(BaseModel):
    # Aggregated latency percentiles
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    # Per-component latency averages (VideoSDK EvalMetric alignment)
    avg_stt_latency_ms: float = 0.0
    avg_llm_latency_ms: float = 0.0
    avg_tts_latency_ms: float = 0.0
    avg_end_to_end_latency_ms: float = 0.0
    # Quality metrics
    intent_recognition_rate: float = 0.0
    instruction_following_rate: float = 0.0
    repetition_rate: float = 0.0
    sentiment_delta: float = 0.0
    named_entity_accuracy: float = 0.0
    tool_call_success_rate: float = 0.0
    hallucination_rate: float = 0.0


class ComponentEvalResult(BaseModel):
    """
    Result from a component-isolation test (STT / LLM / TTS only).
    Mirrors VideoSDK's individual component testing mode.
    """
    component: str                          # "stt" | "llm" | "tts"
    input: str                              # text or audio path
    output: str                             # transcription, response, or audio path
    latency_ms: float
    # STT-specific
    wer: float | None = None
    cer: float | None = None
    # LLM-specific
    judge_scores: list[JudgeScore] = Field(default_factory=list)
    relevance: float | None = None
    reasoning: float | None = None
    clarity: float | None = None
    score_0_10: float | None = None
    # TTS-specific
    audio_duration_seconds: float | None = None
    realtime_factor: float | None = None    # latency / audio_duration (< 1 = faster than real-time)
    # Shared
    model_used: str = ""
    error: str | None = None


class FailureReport(BaseModel):
    eva_a_score: EvaAScore
    eva_x_score: EvaXScore
    failed_criterion: str
    failure_turn_index: int
    failure_excerpt: str
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
    # Evaluation options
    include_context: bool = False   # whether full conversation context was sent to judge

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
        passes = sum(1 for r in self.runs if r.verdict == Verdict.PASS)
        return passes / self.k if self.k > 0 else 0.0

    @property
    def pass_all_k(self) -> float:
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
