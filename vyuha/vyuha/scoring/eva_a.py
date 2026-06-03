from __future__ import annotations

from typing import Any

import structlog

from vyuha.models.scoring import EvaAScore, TurnResult, JudgeScore, JudgeCriterion
from vyuha.models.test_case import TestCase
from vyuha.scoring.judges import LLMJudge

log = structlog.get_logger()

_FAITHFULNESS_PROMPT = """
Evaluate whether the agent's responses are faithful — grounded in the system prompt, tool results, and policy.
Identify any hallucinations (facts stated that are not in the provided context), policy violations, or fabrications.

Score from 0.0 to 1.0:
- 1.0: Perfectly grounded, no hallucinations, all policy constraints respected
- 0.7-0.9: Minor issues (e.g., phrasing imprecision) but no factual hallucinations
- 0.4-0.6: One or more hallucinated facts, or mild policy violation
- 0.0-0.3: Significant hallucination or critical policy violation

Respond with JSON: {"score": <float>, "issues": [<string>], "reason": <string>}
"""

_JUDGE_CRITERIA_PROMPT = """
Evaluate the agent's conversation across four dimensions (VideoSDK-aligned criteria).
Score each from 0-10.

REASONING: Does the agent explain its response logic clearly? Does it justify decisions,
tool calls, or refusals? High scores = transparent reasoning; Low = unexplained actions.

RELEVANCE: Does each agent response directly address what the caller asked or needed?
High = on-topic, solves the user's goal; Low = off-topic, ignores user intent.

CLARITY: Is the agent's spoken language clear and understandable for a voice call?
No jargon, no overly complex sentences, appropriate for the language and accent.
High = crystal clear for voice; Low = confusing or hard to follow.

SCORE: Overall quality rating considering all dimensions above.

Conversation:
{transcript}

User goal: {user_goal}
Pass criteria: {pass_criteria}

Respond with JSON:
{
  "reasoning": {"score": <0-10>, "explanation": <string>},
  "relevance":  {"score": <0-10>, "explanation": <string>},
  "clarity":    {"score": <0-10>, "explanation": <string>},
  "score":      {"score": <0-10>, "explanation": <string>}
}
"""

_SPEECH_FIDELITY_PROMPT = """
Evaluate the agent's spoken audio fidelity. Focus on named entities: confirmation codes, account numbers,
amounts, medication names, dates, and proper nouns. A single wrong digit in a confirmation code = failure.

Score from 0.0 to 1.0:
- 1.0: All entities correctly spoken, clear pronunciation
- 0.7-0.9: Minor pronunciation issue but entities intelligible
- 0.4-0.6: One entity incorrectly spoken or unclear
- 0.0-0.3: Critical entity error (wrong account number, wrong medication name, wrong amount)

Respond with JSON: {"score": <float>, "entity_errors": [<string>], "reason": <string>}
"""


class EvaAScorer:
    """
    Computes EVA-A (Accuracy) score:
    - Task Completion: deterministic ground-truth comparison
    - Faithfulness: LLM-as-Judge hallucination detection
    - Speech Fidelity: LALM-as-Judge audio entity accuracy (transcript-based when no audio)
    """

    def __init__(self, judge: LLMJudge | None = None) -> None:
        self._judge = judge or LLMJudge()

    def score_task_completion(
        self,
        ground_truth: dict[str, Any],
        actual_db_state: dict[str, Any],
    ) -> float:
        """
        Deterministic: compare expected vs actual database end state.
        All required fields must match; missing fields = proportional penalty.
        """
        if not ground_truth:
            return 1.0

        total = len(ground_truth)
        correct = 0
        for key, expected_value in ground_truth.items():
            actual_value = actual_db_state.get(key)
            if actual_value == expected_value:
                correct += 1
            else:
                log.debug(
                    "task_completion_mismatch",
                    field=key,
                    expected=expected_value,
                    actual=actual_value,
                )
        return correct / total

    async def score_faithfulness(
        self,
        turns: list[TurnResult],
        test_case: TestCase,
        system_prompt: str = "",
        tool_results: list[dict[str, Any]] | None = None,
    ) -> float:
        transcript = "\n".join(
            f"User: {t.user_utterance}\nAgent: {t.agent_response}" for t in turns
        )
        context = {
            "system_prompt": system_prompt,
            "tool_results": tool_results or [],
            "transcript": transcript,
            "pass_criteria": test_case.pass_criteria,
            "user_goal": test_case.user_goal,
        }
        result = await self._judge.judge("faithfulness", _FAITHFULNESS_PROMPT, context)
        score = float(result.get("score", 0.0))
        if result.get("issues"):
            log.info("faithfulness_issues_found", issues=result["issues"], test_id=test_case.test_id)
        return max(0.0, min(1.0, score))

    async def score_speech_fidelity(
        self,
        turns: list[TurnResult],
        test_case: TestCase,
    ) -> float:
        """
        When audio is available, use LALM-as-Judge via audio transcript.
        Falls back to transcript-only evaluation.
        """
        transcript = "\n".join(
            f"Turn {t.turn_index} - Agent said: {t.agent_response}" for t in turns
        )
        context = {
            "transcript": transcript,
            "user_goal": test_case.user_goal,
            "critical_entities": self._extract_critical_entities(test_case),
        }
        result = await self._judge.judge("speech_fidelity", _SPEECH_FIDELITY_PROMPT, context)
        score = float(result.get("score", 0.0))
        return max(0.0, min(1.0, score))

    def _extract_critical_entities(self, test_case: TestCase) -> list[str]:
        """Extract named entity types from test case ground truth for focus."""
        entities = []
        for key in test_case.ground_truth_end_state:
            if any(kw in key.lower() for kw in ("code", "number", "amount", "name", "id", "date")):
                entities.append(key)
        return entities

    async def score_judge_criteria(
        self,
        turns: list[TurnResult],
        test_case: TestCase,
    ) -> list[JudgeScore]:
        """
        Score REASONING, RELEVANCE, CLARITY, SCORE (VideoSDK-aligned criteria).
        Returns list of JudgeScore, each 0-10.
        """
        transcript = "\n".join(
            f"User: {t.user_utterance}\nAgent: {t.agent_response}" for t in turns
        )
        prompt = _JUDGE_CRITERIA_PROMPT.format(
            transcript=transcript,
            user_goal=test_case.user_goal,
            pass_criteria=test_case.pass_criteria,
        )
        result = await self._judge.judge("judge_criteria", prompt, {})
        scores: list[JudgeScore] = []
        for criterion in ("reasoning", "relevance", "clarity", "score"):
            entry = result.get(criterion, {})
            try:
                raw_score = float(entry.get("score", 0.0))
                scores.append(JudgeScore(
                    criterion=JudgeCriterion(criterion),
                    score=max(0.0, min(10.0, raw_score)),
                    explanation=str(entry.get("explanation", "")),
                ))
            except Exception:
                scores.append(JudgeScore(criterion=JudgeCriterion(criterion), score=0.0))
        return scores

    async def compute(
        self,
        test_case: TestCase,
        turns: list[TurnResult],
        actual_db_state: dict[str, Any],
        system_prompt: str = "",
        tool_results: list[dict[str, Any]] | None = None,
        include_context: bool = False,
    ) -> EvaAScore:
        task_completion = self.score_task_completion(test_case.ground_truth_end_state, actual_db_state)

        if include_context:
            faithfulness, speech_fidelity, judge_details = await asyncio.gather(
                self.score_faithfulness(turns, test_case, system_prompt, tool_results),
                self.score_speech_fidelity(turns, test_case),
                self.score_judge_criteria(turns, test_case),
            )
            relevance = next((j.normalized for j in judge_details if j.criterion.value == "relevance"), 0.0)
            reasoning = next((j.normalized for j in judge_details if j.criterion.value == "reasoning"), 0.0)
            clarity = next((j.normalized for j in judge_details if j.criterion.value == "clarity"), 0.0)
            overall = next((j.score for j in judge_details if j.criterion.value == "score"), 0.0)
        else:
            faithfulness, speech_fidelity = await asyncio.gather(
                self.score_faithfulness(turns, test_case, system_prompt, tool_results),
                self.score_speech_fidelity(turns, test_case),
            )
            judge_details, relevance, reasoning, clarity, overall = [], 0.0, 0.0, 0.0, 0.0

        return EvaAScore(
            task_completion=task_completion,
            faithfulness=faithfulness,
            speech_fidelity=speech_fidelity,
            relevance=relevance,
            reasoning=reasoning,
            clarity=clarity,
            judge_score_0_10=overall,
            judge_details=judge_details,
        )


import asyncio  # noqa: E402 — after class definition to avoid circular at module load
