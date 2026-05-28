from __future__ import annotations

import asyncio
from typing import Any

from vyuha.models.scoring import EvaXScore, TurnResult
from vyuha.models.test_case import TestCase
from vyuha.scoring.judges import LLMJudge

_CONCISENESS_PROMPT = """
Evaluate whether the agent's responses are appropriately concise for a voice conversation.
Voice users cannot skim — overly long responses cause cognitive overload and poor experience.

Score from 0.0 to 1.0:
- 1.0: Every response is the right length for spoken delivery; no padding or repetition
- 0.7-0.9: Slightly verbose in one or two turns but generally appropriate
- 0.4-0.6: Regularly too verbose, or includes lists/formatting that doesn't translate to voice
- 0.0-0.3: Severely verbose, causes conversation breakdown

Respond with JSON: {"score": <float>, "verbose_turns": [<int>], "reason": <string>}
"""

_PROGRESSION_PROMPT = """
Evaluate whether the conversation moved forward effectively. Look for:
- Stalling: agent asks for already-provided information
- Loops: agent gets stuck repeating the same question
- Context loss: agent forgets what was said earlier in the conversation
- Dead ends: agent can't progress the conversation toward goal completion

Score from 0.0 to 1.0:
- 1.0: Conversation progressed smoothly to goal completion
- 0.7-0.9: Minor backtrack but recovered
- 0.4-0.6: Noticeable stall or context loss that slowed progress
- 0.0-0.3: Conversation stalled entirely or looped without resolution

Respond with JSON: {"score": <float>, "stall_turns": [<int>], "reason": <string>}
"""

_TURN_TAKING_PROMPT = """
Evaluate the agent's turn-taking quality in this voice conversation. Look for:
- Interruptions: agent spoke before user finished
- Excessive silence: agent took too long to respond after user stopped speaking
- Response timing: was the response prompt and natural

Score from 0.0 to 1.0:
- 1.0: Natural turn-taking throughout, no interruptions, no excessive pauses
- 0.7-0.9: One minor timing issue
- 0.4-0.6: Multiple interruptions or pauses that broke conversational flow
- 0.0-0.3: Severely disrupted turn-taking that damaged the conversation

Note: Latency data (ms per turn) is provided — use it to assess timing objectively.

Respond with JSON: {"score": <float>, "problem_turns": [<int>], "reason": <string>}
"""


class EvaXScorer:
    """
    Computes EVA-X (Experience) score:
    - Conciseness: responses appropriately brief for voice
    - Conversation Progression: forward movement, no loops/stalls
    - Turn-Taking: appropriate timing, no interruptions
    """

    def __init__(self, judge: LLMJudge | None = None) -> None:
        self._judge = judge or LLMJudge()

    def _build_transcript_context(
        self, turns: list[TurnResult], test_case: TestCase
    ) -> dict[str, Any]:
        return {
            "user_goal": test_case.user_goal,
            "transcript": [
                {
                    "turn": t.turn_index,
                    "user": t.user_utterance,
                    "agent": t.agent_response,
                    "latency_ms": t.latency_ms,
                }
                for t in turns
            ],
        }

    async def score_conciseness(self, turns: list[TurnResult], test_case: TestCase) -> float:
        ctx = self._build_transcript_context(turns, test_case)
        result = await self._judge.judge("conciseness", _CONCISENESS_PROMPT, ctx)
        return max(0.0, min(1.0, float(result.get("score", 0.0))))

    async def score_progression(self, turns: list[TurnResult], test_case: TestCase) -> float:
        ctx = self._build_transcript_context(turns, test_case)
        result = await self._judge.judge("conversation_progression", _PROGRESSION_PROMPT, ctx)
        return max(0.0, min(1.0, float(result.get("score", 0.0))))

    async def score_turn_taking(self, turns: list[TurnResult], test_case: TestCase) -> float:
        ctx = self._build_transcript_context(turns, test_case)
        result = await self._judge.judge("turn_taking", _TURN_TAKING_PROMPT, ctx)
        return max(0.0, min(1.0, float(result.get("score", 0.0))))

    async def compute(self, test_case: TestCase, turns: list[TurnResult]) -> EvaXScore:
        conciseness, progression, turn_taking = await asyncio.gather(
            self.score_conciseness(turns, test_case),
            self.score_progression(turns, test_case),
            self.score_turn_taking(turns, test_case),
        )
        return EvaXScore(
            conciseness=conciseness,
            conversation_progression=progression,
            turn_taking=turn_taking,
        )
