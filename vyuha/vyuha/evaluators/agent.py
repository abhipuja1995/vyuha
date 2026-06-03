"""Agent-specific evaluators: tool call accuracy, trajectory matching, step count."""
from __future__ import annotations

from typing import Any
from vyuha.evaluators.base import BaseEvaluator, EvalResult


class ToolCallAccuracy(BaseEvaluator):
    """
    Measures what fraction of expected tool calls were actually made.
    Ported from FutureAGI ToolCallAccuracy pattern.

    Args:
        expected_tools: list of tool names that should have been called
        actual_tools:   list of tool names actually called (in TurnResult)
        mode: "exact" (same set), "subset" (all expected ⊆ actual),
              "ordered" (same sequence)
    """
    name = "tool_call_accuracy"
    description = "Fraction of expected tool calls that were made."
    required_keys = ["expected_tools", "actual_tools"]

    def __init__(self, mode: str = "subset") -> None:
        self.mode = mode
        self.pass_threshold = 1.0

    def _evaluate(
        self,
        expected_tools: list[str],
        actual_tools: list[str],
        **_: Any,
    ) -> EvalResult:
        if not expected_tools:
            return EvalResult(value=1.0, reason="No expected tools — trivially correct.")

        if self.mode == "ordered":
            # Sequence must match exactly up to len(expected)
            correct = sum(
                1 for e, a in zip(expected_tools, actual_tools) if e == a
            )
            score = round(correct / len(expected_tools), 4)
            return EvalResult(
                value=score,
                reason=f"Ordered match: {correct}/{len(expected_tools)} tools in sequence.",
                passed=score >= 1.0,
            )

        if self.mode == "exact":
            ok = set(expected_tools) == set(actual_tools)
            return EvalResult(
                value=1.0 if ok else 0.0,
                reason="Exact tool set match." if ok else f"Expected {set(expected_tools)}, got {set(actual_tools)}",
                passed=ok,
            )

        # default: subset — all expected must appear in actual
        missing = [t for t in expected_tools if t not in actual_tools]
        score = round((len(expected_tools) - len(missing)) / len(expected_tools), 4)
        return EvalResult(
            value=score,
            reason=f"Tool coverage: {score}." + (f" Missing: {missing}" if missing else ""),
            passed=not missing,
        )


class TrajectoryMatch(BaseEvaluator):
    """
    Compares agent conversation trajectory against an expected path.
    Supports "exact" (same sequence), "partial" (expected ⊆ actual), "flexible" (fuzzy).

    trajectory: list of dicts with "node_id" or "utterance" keys
    """
    name = "trajectory_match"
    description = "How well the actual conversation path matches the expected trajectory."
    required_keys = ["expected_trajectory", "actual_trajectory"]

    def __init__(self, mode: str = "partial") -> None:
        self.mode = mode
        self.pass_threshold = 0.8

    def _node_id(self, item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("node_id") or item.get("utterance") or item)
        return str(item)

    def _evaluate(
        self,
        expected_trajectory: list[Any],
        actual_trajectory: list[Any],
        **_: Any,
    ) -> EvalResult:
        expected = [self._node_id(n) for n in expected_trajectory]
        actual = [self._node_id(n) for n in actual_trajectory]

        if not expected:
            return EvalResult(value=1.0, reason="No expected trajectory.")

        if self.mode == "exact":
            ok = expected == actual
            return EvalResult(
                value=1.0 if ok else 0.0,
                reason="Exact trajectory match." if ok else f"Expected {expected}, got {actual}",
                passed=ok,
            )

        if self.mode == "partial":
            # Expected nodes must appear in actual (in order, not necessarily consecutive)
            actual_set = set(actual)
            covered = [e for e in expected if e in actual_set]
            # also check order is preserved
            order_ok = True
            prev_idx = -1
            for e in expected:
                try:
                    idx = actual.index(e, prev_idx + 1)
                    prev_idx = idx
                except ValueError:
                    order_ok = False
                    break
            coverage = round(len(covered) / len(expected), 4)
            score = round(coverage * (1.0 if order_ok else 0.8), 4)
            return EvalResult(
                value=score,
                reason=f"Trajectory coverage: {coverage}, order_preserved: {order_ok}",
                passed=score >= (self.pass_threshold or 0.8),
            )

        # flexible: LCS ratio
        m, n = len(expected), len(actual)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                dp[i][j] = dp[i - 1][j - 1] + 1 if expected[i - 1] == actual[j - 1] else max(dp[i - 1][j], dp[i][j - 1])
        lcs = dp[m][n]
        score = round(lcs / max(m, 1), 4)
        return EvalResult(value=score, reason=f"LCS trajectory match: {score} ({lcs}/{m} nodes)")


class StepCount(BaseEvaluator):
    """
    Evaluates whether the agent completed the task in the expected number of turns.
    Pass if actual_steps <= max_steps.
    """
    name = "step_count"
    description = "True if the agent completed within the expected step budget."
    required_keys = ["actual_steps"]

    def __init__(self, max_steps: int = 10, min_steps: int = 1) -> None:
        self.max_steps = max_steps
        self.min_steps = min_steps

    def _evaluate(self, actual_steps: int, **_: Any) -> EvalResult:
        ok = self.min_steps <= actual_steps <= self.max_steps
        return EvalResult(
            value=actual_steps,
            reason=f"Steps: {actual_steps} ({'within' if ok else 'outside'} [{self.min_steps}, {self.max_steps}])",
            passed=ok,
        )
