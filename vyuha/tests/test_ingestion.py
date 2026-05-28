"""Tests for the production call ingestion pipeline (deterministic parts only)."""
from __future__ import annotations

from datetime import datetime

from vyuha.ingestion.failure_detector import detect_failure_signals, _detect_repetition
from vyuha.ingestion.models import FailedCallRecord, FailureSignal


def _make_record(**kwargs) -> FailedCallRecord:
    defaults = dict(
        call_id="CALL-001",
        agent_id="test-agent",
        started_at=datetime(2026, 5, 25, 10, 0),
        ended_at=datetime(2026, 5, 25, 10, 5),
        transcript=[],
        task_completed=False,
    )
    return FailedCallRecord(**{**defaults, **kwargs})


def test_abandonment_detected_when_task_incomplete():
    record = _make_record(task_completed=False)
    signals = detect_failure_signals(record)
    assert FailureSignal.ABANDONMENT in signals


def test_no_abandonment_when_task_complete():
    record = _make_record(task_completed=True)
    signals = detect_failure_signals(record)
    assert FailureSignal.ABANDONMENT not in signals


def test_sentiment_drop_detected_below_threshold():
    record = _make_record(sentiment_scores=[0.8, 0.6, 0.3, 0.25, 0.2])
    signals = detect_failure_signals(record)
    assert FailureSignal.SENTIMENT_DROP in signals


def test_no_sentiment_drop_above_threshold():
    record = _make_record(sentiment_scores=[0.8, 0.7, 0.6, 0.5])
    signals = detect_failure_signals(record)
    assert FailureSignal.SENTIMENT_DROP not in signals


def test_tool_error_detected():
    record = _make_record(tool_call_trace=[
        {"tool": "authenticate_user", "status": "error", "error": "timeout"},
    ])
    signals = detect_failure_signals(record)
    assert FailureSignal.TOOL_ERROR in signals


def test_no_tool_error_when_all_success():
    record = _make_record(tool_call_trace=[
        {"tool": "authenticate_user", "status": "success"},
        {"tool": "get_balance", "status": "success"},
    ])
    signals = detect_failure_signals(record)
    assert FailureSignal.TOOL_ERROR not in signals


def test_repetition_detected_when_user_repeats():
    # Three near-identical user turns → threshold=2 triggers
    transcript = [
        {"role": "user", "text": "I want to check my account balance"},
        {"role": "agent", "text": "I'm sorry, can you repeat?"},
        {"role": "user", "text": "I want to check my account balance please"},
        {"role": "agent", "text": "I'm still not understanding"},
        {"role": "user", "text": "I want to check my account balance now"},
    ]
    record = _make_record(transcript=transcript)
    signals = detect_failure_signals(record)
    assert FailureSignal.REPETITION in signals


def test_no_repetition_on_diverse_turns():
    transcript = [
        {"role": "user", "text": "I want to check my balance"},
        {"role": "agent", "text": "Sure, what is your account number?"},
        {"role": "user", "text": "My account number is 1234567"},
        {"role": "agent", "text": "Verified. Your balance is 5000."},
        {"role": "user", "text": "Thank you, goodbye"},
    ]
    record = _make_record(transcript=transcript, task_completed=True)
    signals = detect_failure_signals(record)
    assert FailureSignal.REPETITION not in signals
    assert FailureSignal.ABANDONMENT not in signals


def test_multiple_signals_combined():
    transcript = [
        {"role": "user", "text": "Balance please"},
        {"role": "agent", "text": "Sorry?"},
        {"role": "user", "text": "Balance please"},
        {"role": "agent", "text": "I cannot help"},
        {"role": "user", "text": "Balance please"},
    ]
    record = _make_record(
        transcript=transcript,
        sentiment_scores=[0.6, 0.4, 0.3, 0.2, 0.1],
        tool_call_trace=[{"tool": "get_balance", "status": "failed"}],
    )
    signals = detect_failure_signals(record)
    assert FailureSignal.REPETITION in signals
    assert FailureSignal.ABANDONMENT in signals
    assert FailureSignal.SENTIMENT_DROP in signals
    assert FailureSignal.TOOL_ERROR in signals


def test_detect_repetition_direct():
    turns = [
        {"role": "user", "text": "check my balance"},
        {"role": "user", "text": "check my balance please"},   # near-duplicate
        {"role": "user", "text": "balance check"},
    ]
    assert _detect_repetition(turns, threshold=1) is True


def test_detect_no_repetition_direct():
    turns = [
        {"role": "user", "text": "check my balance"},
        {"role": "user", "text": "my account number is 1234"},
        {"role": "user", "text": "thank you goodbye"},
    ]
    assert _detect_repetition(turns, threshold=2) is False
