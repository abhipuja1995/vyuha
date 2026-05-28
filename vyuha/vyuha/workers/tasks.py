"""
Celery tasks for async test execution.
Each task runs a single test case against the VAUT, scores it, and persists the result.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

import structlog

from vyuha.workers.celery_app import app

log = structlog.get_logger()


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(bind=True, name="vyuha.run_test_case", max_retries=2)
def run_test_case(
    self,
    test_id: str,
    vaut_url: str | None,
    mode: str,
    seed: int | None,
) -> dict[str, Any]:
    """
    Execute a single test case run.
    Persists result to PostgreSQL and returns a summary dict.
    """
    return _run_async(_async_run_test_case(self, test_id, vaut_url, mode, seed))


async def _async_run_test_case(
    task,
    test_id: str,
    vaut_url: str | None,
    mode: str,
    seed: int | None,
) -> dict[str, Any]:
    from vyuha.db.engine import AsyncSessionLocal
    from vyuha.db.repositories import TestCaseRepo, RunRepo
    from vyuha.orchestrator.runner import execute_single_run

    run_id = str(uuid.uuid4())
    log.info("worker_run_starting", task_id=task.request.id, test_id=test_id, run_id=run_id)

    async with AsyncSessionLocal() as db:
        tc_repo = TestCaseRepo(db)
        run_repo = RunRepo(db)

        test_case = await tc_repo.get(test_id)
        if not test_case:
            raise ValueError(f"Test case not found: {test_id}")

        result = await execute_single_run(test_case, mode=mode, vaut_url=vaut_url, seed=seed)
        await run_repo.save(result)

    log.info(
        "worker_run_complete",
        run_id=result.run_id,
        verdict=result.verdict,
        eva_a=result.eva_a.composite,
    )
    return {
        "run_id": result.run_id,
        "verdict": result.verdict.value,
        "eva_a": result.eva_a.composite,
        "eva_x": result.eva_x.composite,
    }


@app.task(name="vyuha.run_regression_suite")
def run_regression_suite(tag: str = "regression", fail_below: float = 0.97) -> dict[str, Any]:
    """Triggered by CI/CD: runs all test cases with a given tag in parallel."""
    return _run_async(_async_run_regression_suite(tag, fail_below))


async def _async_run_regression_suite(tag: str, fail_below: float) -> dict[str, Any]:
    from vyuha.db.engine import AsyncSessionLocal
    from vyuha.db.repositories import TestCaseRepo, RunRepo
    from vyuha.orchestrator.runner import execute_single_run
    from vyuha.models.scoring import Verdict

    async with AsyncSessionLocal() as db:
        tc_repo = TestCaseRepo(db)
        run_repo = RunRepo(db)
        test_cases = await tc_repo.list(tag=tag, limit=500)

    if not test_cases:
        return {"error": f"No test cases tagged '{tag}'", "gate_passed": False}

    async def run_one(tc):
        async with AsyncSessionLocal() as db:
            run_repo = RunRepo(db)
            result = await execute_single_run(tc, mode="text")
            await run_repo.save(result)
            return result

    results = await asyncio.gather(*[run_one(tc) for tc in test_cases])
    total = len(results)
    passed = sum(1 for r in results if r.verdict == Verdict.PASS)
    pass_rate = passed / total if total else 0.0
    critical = sum(
        1 for r in results
        if r.failure_report and any(t.is_critical for t in r.failure_report.rca_tags)
    )
    gate_passed = pass_rate >= fail_below and critical == 0

    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(pass_rate, 4),
        "critical_failures": critical,
        "gate_passed": gate_passed,
        "tag": tag,
    }
