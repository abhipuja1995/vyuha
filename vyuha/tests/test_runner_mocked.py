"""
Tests for execute_single_run() — the core orchestration loop.
All external dependencies (UserSimulator, LLM judges) are mocked.
Covers: PASS/FAIL verdicts, ERROR handling, failure report generation,
latency diagnostics, and critical safety path.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from vyuha.models.scoring import (
    EvaAScore, EvaXScore, DiagnosticMetrics, Verdict, TurnResult,
)
from vyuha.models.rca import RCACode, RCATag
from vyuha.models.test_case import (
    TestCase, TestCategory, PersonaConfig, Language, NoiseProfile, Emotion,
    ConversationGraph, ConversationNode, ConversationEdge, ToolCallSpec,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_tc(category: TestCategory = TestCategory.HAPPY_PATH) -> TestCase:
    return TestCase(
        title="Runner test case",
        category=category,
        user_goal="Check account balance",
        persona_config=PersonaConfig(language=Language.TELUGU),
        conversation_graph=ConversationGraph(
            start_node="req",
            nodes=[
                ConversationNode(node_id="req", utterance_template="Balance cheppandi"),
                ConversationNode(node_id="done", utterance_template="Dhanyavaadalu", is_terminal=True),
            ],
            edges=[ConversationEdge(from_node="req", to_node="done", condition="balance")],
        ),
        ground_truth_end_state={"balance_shown": True},
        pass_criteria="Balance shown without hallucination",
        tags=["telugu", "regression"],
    )


def _make_turns(latencies: list[float] = None) -> list[TurnResult]:
    latencies = latencies or [200.0, 350.0]
    return [
        TurnResult(
            turn_index=i,
            user_utterance=f"User turn {i}",
            agent_response=f"Agent response {i}",
            latency_ms=lat,
        )
        for i, lat in enumerate(latencies)
    ]


def _passing_eva_a() -> EvaAScore:
    return EvaAScore(task_completion=1.0, faithfulness=1.0, speech_fidelity=1.0)


def _failing_eva_a() -> EvaAScore:
    return EvaAScore(task_completion=0.3, faithfulness=0.3, speech_fidelity=0.3)


def _neutral_eva_x() -> EvaXScore:
    return EvaXScore(conciseness=0.9, conversation_progression=0.9, turn_taking=0.85)


# ─── Runner: PASS verdict ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_runner_pass_verdict_when_eva_a_passes():
    tc = _make_tc()
    turns = _make_turns()

    with (
        patch("vyuha.simulator.user_simulator.UserSimulator") as MockSim,
        patch("vyuha.orchestrator.runner._eva_a") as mock_eva_a,
        patch("vyuha.orchestrator.runner._eva_x") as mock_eva_x,
        patch("vyuha.orchestrator.runner._rca") as mock_rca,
    ):
        mock_instance = AsyncMock()
        mock_instance.run.return_value = turns
        MockSim.return_value = mock_instance

        mock_eva_a.compute = AsyncMock(return_value=_passing_eva_a())
        mock_eva_x.compute = AsyncMock(return_value=_neutral_eva_x())

        from vyuha.orchestrator.runner import execute_single_run
        result = await execute_single_run(tc)

    assert result.verdict == Verdict.PASS
    assert result.failure_report is None
    assert result.eva_a.composite == pytest.approx(1.0)


# ─── Runner: FAIL verdict + failure report ────────────────────────────────────

@pytest.mark.asyncio
async def test_runner_fail_verdict_generates_failure_report():
    tc = _make_tc()
    turns = _make_turns()

    with (
        patch("vyuha.simulator.user_simulator.UserSimulator") as MockSim,
        patch("vyuha.orchestrator.runner._eva_a") as mock_eva_a,
        patch("vyuha.orchestrator.runner._eva_x") as mock_eva_x,
        patch("vyuha.orchestrator.runner._rca") as mock_rca,
    ):
        mock_instance = AsyncMock()
        mock_instance.run.return_value = turns
        MockSim.return_value = mock_instance

        mock_eva_a.compute = AsyncMock(return_value=_failing_eva_a())
        mock_eva_x.compute = AsyncMock(return_value=_neutral_eva_x())

        # RCA returns no critical tags
        rca_tag = RCATag.from_code(RCACode.LLM_HALLUCINATION, turn_index=1, confidence=0.8)
        mock_rca.tag = AsyncMock(return_value=([rca_tag], 1, "Agent hallucinated pricing"))

        from vyuha.orchestrator.runner import execute_single_run
        result = await execute_single_run(tc)

    assert result.verdict == Verdict.FAIL
    assert result.failure_report is not None
    assert result.failure_report.failure_turn_index == 1
    assert "hallucinated" in result.failure_report.failure_excerpt.lower()


# ─── Runner: ERROR when simulator raises ─────────────────────────────────────

@pytest.mark.asyncio
async def test_runner_returns_error_verdict_on_simulator_exception():
    tc = _make_tc()

    with patch("vyuha.simulator.user_simulator.UserSimulator") as MockSim:
        mock_instance = AsyncMock()
        mock_instance.run.side_effect = RuntimeError("TTS provider unavailable")
        MockSim.return_value = mock_instance

        from vyuha.orchestrator.runner import execute_single_run
        result = await execute_single_run(tc)

    assert result.verdict == Verdict.ERROR
    assert result.error_message is not None
    assert "TTS provider unavailable" in result.error_message
    assert result.eva_a.composite == pytest.approx(0.0)


# ─── Runner: latency diagnostics ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_runner_computes_latency_diagnostics():
    tc = _make_tc()
    # 10 turns with increasing latencies to test p50/p95 calculation
    latencies = [100.0 * (i + 1) for i in range(10)]
    turns = _make_turns(latencies)

    with (
        patch("vyuha.simulator.user_simulator.UserSimulator") as MockSim,
        patch("vyuha.orchestrator.runner._eva_a") as mock_eva_a,
        patch("vyuha.orchestrator.runner._eva_x") as mock_eva_x,
        patch("vyuha.orchestrator.runner._rca"),
    ):
        mock_instance = AsyncMock()
        mock_instance.run.return_value = turns
        MockSim.return_value = mock_instance
        mock_eva_a.compute = AsyncMock(return_value=_passing_eva_a())
        mock_eva_x.compute = AsyncMock(return_value=_neutral_eva_x())

        from vyuha.orchestrator.runner import execute_single_run
        result = await execute_single_run(tc)

    # Sorted latencies: [100,200,...,1000]. p50 = index 5 = 600ms, p95 = index 9 = 1000ms
    assert result.diagnostics.latency_p50_ms == pytest.approx(600.0)
    assert result.diagnostics.latency_p95_ms == pytest.approx(1000.0)


# ─── Runner: critical safety violation ───────────────────────────────────────

@pytest.mark.asyncio
async def test_runner_critical_safety_tag_sets_failure_criterion():
    """When RCA finds a SAFETY_VIOLATION tag, failure_report reflects 'CRITICAL safety violation'."""
    tc = _make_tc(category=TestCategory.CRITICAL)
    turns = _make_turns()

    with (
        patch("vyuha.simulator.user_simulator.UserSimulator") as MockSim,
        patch("vyuha.orchestrator.runner._eva_a") as mock_eva_a,
        patch("vyuha.orchestrator.runner._eva_x") as mock_eva_x,
        patch("vyuha.orchestrator.runner._rca") as mock_rca,
    ):
        mock_instance = AsyncMock()
        mock_instance.run.return_value = turns
        MockSim.return_value = mock_instance

        mock_eva_a.compute = AsyncMock(return_value=_failing_eva_a())
        mock_eva_x.compute = AsyncMock(return_value=_neutral_eva_x())

        safety_tag = RCATag.from_code(RCACode.SAFETY_VIOLATION, turn_index=0, confidence=0.99)
        assert safety_tag.is_critical
        mock_rca.tag = AsyncMock(return_value=([safety_tag], 0, "Agent provided dosage when should not"))

        from vyuha.orchestrator.runner import execute_single_run
        result = await execute_single_run(tc)

    assert result.verdict == Verdict.FAIL
    assert result.failure_report is not None
    assert "CRITICAL" in result.failure_report.failed_criterion


# ─── Runner: run_id and timing fields populated ───────────────────────────────

@pytest.mark.asyncio
async def test_runner_populates_run_id_and_test_id():
    tc = _make_tc()
    turns = _make_turns()

    with (
        patch("vyuha.simulator.user_simulator.UserSimulator") as MockSim,
        patch("vyuha.orchestrator.runner._eva_a") as mock_eva_a,
        patch("vyuha.orchestrator.runner._eva_x") as mock_eva_x,
        patch("vyuha.orchestrator.runner._rca"),
    ):
        mock_instance = AsyncMock()
        mock_instance.run.return_value = turns
        MockSim.return_value = mock_instance
        mock_eva_a.compute = AsyncMock(return_value=_passing_eva_a())
        mock_eva_x.compute = AsyncMock(return_value=_neutral_eva_x())

        from vyuha.orchestrator.runner import execute_single_run
        result = await execute_single_run(tc)

    assert result.run_id  # non-empty UUID
    assert result.test_id == tc.test_id
    assert result.completed_at >= result.started_at
    assert result.latency_ms >= 0
