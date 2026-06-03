"""ASR / audio evaluators — WER, CER, MER, WIL, WIP."""
from __future__ import annotations

from typing import Any
from vyuha.evaluators.base import BaseEvaluator, EvalResult


def _jiwer_process(reference: str, hypothesis: str):
    try:
        import jiwer
        out = jiwer.process_words(reference, hypothesis)
        return out.substitutions, out.deletions, out.insertions, len(reference.split()), len(hypothesis.split())
    except ImportError:
        # minimal edit distance fallback
        ref, hyp = reference.split(), hypothesis.split()
        m, n = len(ref), len(hyp)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1): dp[i][0] = i
        for j in range(n + 1): dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if ref[i - 1] == hyp[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[m][n], 0, 0, m, n


class WordErrorRate(BaseEvaluator):
    name = "word_error_rate"
    description = "WER = (S+D+I) / max(N,M). Lower is better."
    required_keys = ["output", "expected"]

    def __init__(self, pass_threshold: float | None = 0.2) -> None:
        self.pass_threshold = pass_threshold  # pass if WER ≤ threshold (inverted)

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        S, D, I, N, M = _jiwer_process(expected, output)
        denom = max(N, M, 1)
        wer = round((S + D + I) / denom, 4)
        # for pass/fail: pass if WER is LOW (≤ threshold)
        if self.pass_threshold is not None:
            self.passed = wer <= self.pass_threshold
        return EvalResult(
            value=wer,
            reason=f"WER: {wer} (S={S}, D={D}, I={I}, N={N})",
            passed=(wer <= self.pass_threshold) if self.pass_threshold is not None else None,
        )

    def run(self, **kwargs: Any) -> EvalResult:
        import time
        t0 = time.monotonic()
        result = self._evaluate(**kwargs)
        result.runtime_ms = (time.monotonic() - t0) * 1000
        return result


class CharacterErrorRate(BaseEvaluator):
    name = "character_error_rate"
    description = "CER on character-level edit distance."
    required_keys = ["output", "expected"]

    def __init__(self, pass_threshold: float | None = 0.15) -> None:
        self.pass_threshold = pass_threshold

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        try:
            import jiwer
            out = jiwer.process_characters(expected, output)
            S, D, I = out.substitutions, out.deletions, out.insertions
            N, M = len(expected), len(output)
        except ImportError:
            a, b = list(expected), list(output)
            m, n = len(a), len(b)
            dp = list(range(n + 1))
            for i in range(1, m + 1):
                prev = dp[:]
                dp[0] = i
                for j in range(1, n + 1):
                    dp[j] = prev[j - 1] if a[i - 1] == b[j - 1] else 1 + min(prev[j], dp[j - 1], prev[j - 1])
            S, D, I, N, M = dp[n], 0, 0, m, n
        denom = max(N, M, 1)
        cer = round((S + D + I) / denom, 4)
        return EvalResult(
            value=cer,
            reason=f"CER: {cer}",
            passed=(cer <= self.pass_threshold) if self.pass_threshold is not None else None,
        )

    def run(self, **kwargs: Any) -> EvalResult:
        import time; t0 = time.monotonic()
        result = self._evaluate(**kwargs)
        result.runtime_ms = (time.monotonic() - t0) * 1000
        return result


class MatchErrorRate(BaseEvaluator):
    name = "match_error_rate"
    description = "MER = (S+D+I) / (S+D+H). Accounts for correct matches."
    required_keys = ["output", "expected"]

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        S, D, I, N, M = _jiwer_process(expected, output)
        H = N - S - D  # correct hits
        denom = max(S + D + H, 1)
        mer = round((S + D + I) / denom, 4)
        return EvalResult(value=mer, reason=f"MER: {mer}")


class WordInfoLost(BaseEvaluator):
    name = "word_info_lost"
    description = "WIL — fraction of word information lost (complement of WIP)."
    required_keys = ["output", "expected"]

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        S, D, I, N, M = _jiwer_process(expected, output)
        H = N - S - D
        wil = round(1.0 - (H * H) / max(N * M, 1), 4)
        return EvalResult(value=wil, reason=f"WIL: {wil}")


class WordInfoPreserved(BaseEvaluator):
    name = "word_info_preserved"
    description = "WIP — fraction of word information preserved."
    required_keys = ["output", "expected"]

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        S, D, I, N, M = _jiwer_process(expected, output)
        H = N - S - D
        wip = round((H * H) / max(N * M, 1), 4)
        return EvalResult(value=wip, reason=f"WIP: {wip}")
