from __future__ import annotations

from collections import Counter
from typing import Any

from vyuha.ingestion.models import FailedCallRecord, FailureSignal


def detect_failure_signals(record: FailedCallRecord) -> list[FailureSignal]:
    """
    Deterministic failure signal detection from call trace.
    Returns all triggered signals — caller decides minimum threshold for ingestion.
    """
    signals: list[FailureSignal] = list(record.failure_signals)  # keep any pre-labelled signals

    # Repetition: user said essentially the same thing more than twice
    if _detect_repetition(record.transcript):
        _add_unique(signals, FailureSignal.REPETITION)

    # Abandonment: call ended without task completion
    if not record.task_completed:
        _add_unique(signals, FailureSignal.ABANDONMENT)

    # Sentiment drop below 0.35
    if record.sentiment_scores:
        final_sentiment = record.sentiment_scores[-1]
        if final_sentiment < 0.35:
            _add_unique(signals, FailureSignal.SENTIMENT_DROP)

    # Tool error in trace
    if _detect_tool_error(record.tool_call_trace):
        _add_unique(signals, FailureSignal.TOOL_ERROR)

    return signals


def _add_unique(signals: list[FailureSignal], signal: FailureSignal) -> None:
    if signal not in signals:
        signals.append(signal)


def _detect_repetition(transcript: list[dict[str, str]], threshold: int = 2) -> bool:
    """
    Count how many times a user turn is a near-duplicate of an earlier user turn.
    Uses normalized token overlap (Jaccard similarity > 0.7 = duplicate).
    """
    import re
    def _tokenize(text: str) -> set[str]:
        return set(re.sub(r"[^\w\s]", "", text.lower()).split())

    user_turns = [t["text"] for t in transcript if t.get("role") == "user"]
    if len(user_turns) < threshold + 1:
        return False

    repeat_count = 0
    for i, turn in enumerate(user_turns):
        tokens_a = _tokenize(turn)
        for j in range(i):
            tokens_b = _tokenize(user_turns[j])
            if not tokens_a or not tokens_b:
                continue
            union = tokens_a | tokens_b
            intersection = tokens_a & tokens_b
            similarity = len(intersection) / len(union)
            if similarity >= 0.7:
                repeat_count += 1
                break  # count this turn as repeated once, move on

    return repeat_count >= threshold


def _detect_tool_error(trace: list[dict[str, Any]]) -> bool:
    """Check tool call trace for errors or exceptions."""
    for entry in trace:
        if entry.get("status") in ("error", "exception", "failed"):
            return True
        if entry.get("error") is not None:
            return True
    return False
