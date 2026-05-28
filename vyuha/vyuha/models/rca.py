from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class RCACode(str, Enum):
    # Speech Recognition
    ASR_ENTITY_MISHEAR = "RCA-ASR-01"      # Misheard named entity (account number, med name)
    ASR_NOISE_FAILURE = "RCA-ASR-02"       # Failed under noise conditions

    # Language & Accent
    LANG_CODE_SWITCH_FAIL = "RCA-LANG-01"  # Failed to understand code-switched utterance
    LANG_WRONG_RESPONSE = "RCA-LANG-02"    # Responded in wrong language

    # LLM Reasoning
    LLM_HALLUCINATION = "RCA-LLM-01"      # Fabricated fact not grounded in prompt/tools
    LLM_INSTRUCTION_MISS = "RCA-LLM-02"   # Missed a step in multi-step instructions
    LLM_POLICY_VIOLATION = "RCA-LLM-03"   # Violated a policy constraint

    # Conversation Flow
    FLOW_LOOP = "RCA-FLOW-01"             # Stuck in loop / asked for already-given info
    FLOW_INTERRUPT_FAIL = "RCA-FLOW-02"   # Did not handle interruption gracefully

    # Tool / Integration
    TOOL_FAILURE = "RCA-TOOL-01"          # Tool call failed or unexpected response

    # Latency
    LATENCY_BREACH = "RCA-LAT-01"         # Response latency exceeded threshold

    # Safety / Compliance
    SAFETY_VIOLATION = "RCA-SAFE-01"      # Unsafe or non-compliant response (CRITICAL)


_RCA_DESCRIPTIONS: dict[RCACode, tuple[str, str]] = {
    RCACode.ASR_ENTITY_MISHEAR: (
        "ASR misheard a named entity",
        "Improve STT fine-tuning or add custom vocabulary",
    ),
    RCACode.ASR_NOISE_FAILURE: (
        "ASR failed under noise conditions",
        "Test and switch STT provider for that noise profile",
    ),
    RCACode.LANG_CODE_SWITCH_FAIL: (
        "Agent failed to understand code-switched utterance",
        "Retrain on code-switching corpus for that language pair",
    ),
    RCACode.LANG_WRONG_RESPONSE: (
        "Agent responded in wrong language",
        "Update language-detection logic in agent prompt",
    ),
    RCACode.LLM_HALLUCINATION: (
        "Agent hallucinated a fact not present in tools or prompt",
        "Add grounding constraints to system prompt; add RAG guardrails",
    ),
    RCACode.LLM_INSTRUCTION_MISS: (
        "Agent failed to follow multi-step instructions",
        "Break complex instructions into explicit ordered steps in prompt",
    ),
    RCACode.LLM_POLICY_VIOLATION: (
        "Agent violated a policy constraint",
        "Strengthen negative constraints in system prompt with examples",
    ),
    RCACode.FLOW_LOOP: (
        "Agent got stuck in a loop or asked for already-provided information",
        "Review context retention; check memory window configuration",
    ),
    RCACode.FLOW_INTERRUPT_FAIL: (
        "Agent did not handle caller interruption gracefully",
        "Add interruption handling to flow logic",
    ),
    RCACode.TOOL_FAILURE: (
        "Tool call failed or returned unexpected response",
        "Fix tool integration; add fallback handling in agent",
    ),
    RCACode.LATENCY_BREACH: (
        "Response latency exceeded threshold causing conversation breakdown",
        "Optimise LLM inference path or switch to faster model tier",
    ),
    RCACode.SAFETY_VIOLATION: (
        "Agent provided unsafe or non-compliant response",
        "CRITICAL: immediate escalation to compliance team required",
    ),
}


class RCATag(BaseModel):
    code: RCACode
    description: str
    suggested_fix: str
    turn_index: int | None = None          # which conversation turn triggered this
    confidence: float = 1.0               # 0-1, LLM-assigned confidence

    @classmethod
    def from_code(cls, code: RCACode, turn_index: int | None = None, confidence: float = 1.0) -> "RCATag":
        desc, fix = _RCA_DESCRIPTIONS[code]
        return cls(code=code, description=desc, suggested_fix=fix, turn_index=turn_index, confidence=confidence)

    @property
    def is_critical(self) -> bool:
        return self.code == RCACode.SAFETY_VIOLATION
