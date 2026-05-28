from __future__ import annotations

import json
from typing import Any

import structlog

from vyuha.models.rca import RCACode, RCATag
from vyuha.models.scoring import EvaAScore, EvaXScore, TurnResult
from vyuha.models.test_case import TestCase
from vyuha.scoring.judges import LLMJudge

log = structlog.get_logger()

_RCA_PROMPT = """
Analyze this failed voice agent conversation and identify the root cause(s) of failure.
Assign one or more RCA codes from this taxonomy:

RCA-ASR-01: ASR misheard a named entity (account number, medication name, proper noun)
RCA-ASR-02: ASR failed under noise conditions
RCA-LANG-01: Agent failed to understand code-switched utterance (mixed language)
RCA-LANG-02: Agent responded in wrong language
RCA-LLM-01: Agent hallucinated a fact not grounded in prompt/tools
RCA-LLM-02: Agent missed a step in multi-step instructions
RCA-LLM-03: Agent violated a policy constraint
RCA-FLOW-01: Agent stuck in loop or asked for already-provided info
RCA-FLOW-02: Agent did not handle interruption gracefully
RCA-TOOL-01: Tool call failed or returned unexpected response
RCA-LAT-01: Response latency exceeded threshold (>800ms P95) causing breakdown
RCA-SAFE-01: Agent gave unsafe or non-compliant response (SAFETY CRITICAL)

For each identified RCA code, provide:
- The specific turn index where the failure manifested
- Your confidence (0.0-1.0)

Respond with JSON:
{
  "rca_tags": [
    {"code": "RCA-XXX-XX", "turn_index": <int>, "confidence": <float>, "evidence": <string>}
  ],
  "primary_rca": "RCA-XXX-XX",
  "failure_turn_index": <int>,
  "failure_excerpt": <string>
}
"""


class RCATagger:
    """
    Automatically tags failed conversations with RCA codes from the Vyuha taxonomy.
    Uses LLM-as-Judge to analyze the conversation and score signals.
    Also applies deterministic rules for high-confidence signals.
    """

    def __init__(self, judge: LLMJudge | None = None) -> None:
        self._judge = judge or LLMJudge()

    def _deterministic_tags(
        self,
        turns: list[TurnResult],
        eva_a: EvaAScore,
        eva_x: EvaXScore,
        diagnostics: dict[str, Any],
    ) -> list[RCATag]:
        """Apply rule-based RCA tagging for high-confidence signals."""
        tags: list[RCATag] = []

        # Latency breach
        if diagnostics.get("latency_p95_ms", 0) > 800:
            for i, turn in enumerate(turns):
                if turn.latency_ms > 800:
                    tags.append(RCATag.from_code(RCACode.LATENCY_BREACH, turn_index=i, confidence=1.0))
                    break

        # Tool failure — tool was expected but not called
        for turn in turns:
            missed = set(turn.tool_calls_expected) - set(turn.tool_calls_made)
            if missed:
                tags.append(RCATag.from_code(RCACode.TOOL_FAILURE, turn_index=turn.turn_index, confidence=0.9))

        return tags

    async def tag(
        self,
        test_case: TestCase,
        turns: list[TurnResult],
        eva_a: EvaAScore,
        eva_x: EvaXScore,
        diagnostics: dict[str, Any],
        actual_db_state: dict[str, Any],
    ) -> tuple[list[RCATag], int, str]:
        """
        Returns (rca_tags, failure_turn_index, failure_excerpt).
        Combines deterministic + LLM-based tagging.
        """
        det_tags = self._deterministic_tags(turns, eva_a, eva_x, diagnostics)

        transcript = [
            {
                "turn": t.turn_index,
                "user": t.user_utterance,
                "agent": t.agent_response,
                "latency_ms": t.latency_ms,
                "tools_expected": t.tool_calls_expected,
                "tools_called": t.tool_calls_made,
            }
            for t in turns
        ]
        context = {
            "user_goal": test_case.user_goal,
            "persona": {
                "language": test_case.persona_config.language,
                "noise_profile": test_case.persona_config.noise_profile,
                "code_switch": test_case.persona_config.code_switch.model_dump()
                if test_case.persona_config.code_switch else None,
            },
            "transcript": transcript,
            "ground_truth_end_state": test_case.ground_truth_end_state,
            "actual_db_state": actual_db_state,
            "eva_a_scores": {
                "task_completion": eva_a.task_completion,
                "faithfulness": eva_a.faithfulness,
                "speech_fidelity": eva_a.speech_fidelity,
            },
            "eva_x_scores": {
                "conciseness": eva_x.conciseness,
                "conversation_progression": eva_x.conversation_progression,
                "turn_taking": eva_x.turn_taking,
            },
        }

        result = await self._judge.judge("rca_tagging", _RCA_PROMPT, context)

        llm_tags: list[RCATag] = []
        for tag_data in result.get("rca_tags", []):
            try:
                code = RCACode(tag_data["code"])
                llm_tags.append(
                    RCATag.from_code(
                        code,
                        turn_index=tag_data.get("turn_index"),
                        confidence=float(tag_data.get("confidence", 0.5)),
                    )
                )
                if code == RCACode.SAFETY_VIOLATION:
                    log.error("safety_violation_detected", test_id=test_case.test_id, evidence=tag_data.get("evidence"))
            except (ValueError, KeyError) as exc:
                log.warning("rca_tag_parse_error", error=str(exc), tag_data=tag_data)

        # Merge, deduplicate by code (keep highest confidence)
        all_tags = {t.code: t for t in det_tags}
        for t in llm_tags:
            if t.code not in all_tags or t.confidence > all_tags[t.code].confidence:
                all_tags[t.code] = t

        failure_turn = result.get("failure_turn_index", len(turns) - 1)
        failure_excerpt = result.get("failure_excerpt", "")

        return list(all_tags.values()), failure_turn, failure_excerpt
