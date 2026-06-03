"""Base evaluator class and result type."""
from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalResult:
    value: float | bool | str           # the score (0-1 float, bool, or string)
    reason: str = ""                    # human-readable explanation
    passed: bool | None = None          # None = no pass threshold configured
    runtime_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "reason": self.reason,
            "passed": self.passed,
            "runtime_ms": round(self.runtime_ms, 2),
            "metadata": self.metadata,
        }


class BaseEvaluator(ABC):
    """
    Base class for all Vyuha evaluators (ported from FutureAGI BaseEvaluator pattern).

    Subclasses implement `_evaluate(**kwargs) -> EvalResult`.
    `run()` wraps with timing; `run_batch()` parallelises.
    """

    name: str = "base"
    description: str = ""
    required_keys: list[str] = []
    pass_threshold: float | None = None   # set to enable pass/fail

    def _evaluate(self, **kwargs: Any) -> EvalResult:
        raise NotImplementedError

    def run(self, **kwargs: Any) -> EvalResult:
        import time
        t0 = time.monotonic()
        result = self._evaluate(**kwargs)
        result.runtime_ms = (time.monotonic() - t0) * 1000
        if self.pass_threshold is not None and isinstance(result.value, (int, float)):
            result.passed = float(result.value) >= self.pass_threshold
        return result

    def run_batch(
        self,
        data: list[dict[str, Any]],
        max_parallel: int = 8,
    ) -> list[EvalResult]:
        """Run eval over a list of input dicts, preserving order."""
        results: list[EvalResult | None] = [None] * len(data)
        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            futures = {pool.submit(self.run, **row): i for i, row in enumerate(data)}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    results[idx] = EvalResult(
                        value=False, reason=f"Error: {exc}", passed=False
                    )
        return results  # type: ignore[return-value]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required_keys": self.required_keys,
            "pass_threshold": self.pass_threshold,
        }
