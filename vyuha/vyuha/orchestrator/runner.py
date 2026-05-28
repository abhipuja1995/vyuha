"""
Shared run execution logic — used by Celery workers and the API's BackgroundTasks.
Separated from the routes to avoid circular imports.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

import structlog

from vyuha.config import settings
from vyuha.models.scoring import (
    RunResult, EvaAScore, EvaXScore, DiagnosticMetrics, FailureReport, Verdict,
)
from vyuha.models.test_case import TestCase
from vyuha.scoring import EvaAScorer, EvaXScorer, RCATagger

log = structlog.get_logger()

_eva_a = EvaAScorer()
_eva_x = EvaXScorer()
_rca = RCATagger()


async def execute_single_run(
    test_case: TestCase,
    mode: str = "text",
    vaut_url: str | None = None,
    seed: int | None = None,
) -> RunResult:
    """
    Core run execution: simulator → scoring → RCA tagging → RunResult.
    No DB access — caller is responsible for persistence.
    """
    from vyuha.simulator.user_simulator import UserSimulator

    run_id = str(uuid.uuid4())
    started_at = datetime.utcnow()

    simulator = UserSimulator(vaut_url=vaut_url, seed=seed)

    try:
        turns = await simulator.run(
            graph=test_case.conversation_graph,
            persona=test_case.persona_config,
            test_id=test_case.test_id,
            mode=mode,
        )
    except Exception as exc:
        log.error("simulator_error", run_id=run_id, test_id=test_case.test_id, error=str(exc))
        return RunResult(
            run_id=run_id,
            test_id=test_case.test_id,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            verdict=Verdict.ERROR,
            eva_a=EvaAScore(task_completion=0, faithfulness=0, speech_fidelity=0),
            eva_x=EvaXScore(conciseness=0, conversation_progression=0, turn_taking=0),
            diagnostics=DiagnosticMetrics(),
            error_message=str(exc),
        )

    actual_db_state: dict[str, Any] = {}

    latencies = sorted(t.latency_ms for t in turns)
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

    diagnostics = DiagnosticMetrics(latency_p50_ms=p50, latency_p95_ms=p95, tool_call_success_rate=1.0)

    eva_a, eva_x = await asyncio.gather(
        _eva_a.compute(test_case, turns, actual_db_state),
        _eva_x.compute(test_case, turns),
    )

    verdict = Verdict.PASS if eva_a.passes else Verdict.FAIL

    failure_report = None
    if verdict == Verdict.FAIL:
        rca_tags, failure_turn, failure_excerpt = await _rca.tag(
            test_case=test_case,
            turns=turns,
            eva_a=eva_a,
            eva_x=eva_x,
            diagnostics={"latency_p95_ms": p95},
            actual_db_state=actual_db_state,
        )
        failed_criterion = (
            "CRITICAL safety violation"
            if any(t.is_critical for t in rca_tags)
            else f"EVA-A {eva_a.composite:.2f} < threshold {settings.eva_a_pass_threshold}"
        )
        failure_report = FailureReport(
            eva_a_score=eva_a,
            eva_x_score=eva_x,
            failed_criterion=failed_criterion,
            failure_turn_index=failure_turn,
            failure_excerpt=failure_excerpt,
            rca_tags=rca_tags,
        )
        if any(t.is_critical for t in rca_tags):
            log.error("critical_violation", test_id=test_case.test_id, run_id=run_id)

    return RunResult(
        run_id=run_id,
        test_id=test_case.test_id,
        started_at=started_at,
        completed_at=datetime.utcnow(),
        verdict=verdict,
        eva_a=eva_a,
        eva_x=eva_x,
        diagnostics=diagnostics,
        turns=turns,
        final_db_state=actual_db_state,
        failure_report=failure_report,
        judge_model_used=settings.default_judge_model,
    )
