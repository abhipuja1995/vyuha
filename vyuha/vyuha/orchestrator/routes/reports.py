from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.db import RunRepo, get_db

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/summary")
async def run_summary(db: DbDep) -> dict[str, Any]:
    repo = RunRepo(db)
    stats = await repo.summary_stats()
    critical = await repo.count_critical_failures()
    stats["critical_failures"] = critical
    from vyuha.config import settings
    stats["regression_threshold"] = settings.regression_pass_rate
    return stats


@router.get("/rca-breakdown")
async def rca_breakdown(db: DbDep) -> dict[str, Any]:
    return await RunRepo(db).rca_breakdown()


@router.get("/regression-delta")
async def regression_delta(
    db: DbDep,
    baseline_tag: str = "baseline",
    current_tag: str = "regression",
) -> dict[str, Any]:
    from sqlalchemy import select
    from vyuha.db.tables import RunRow, TestCaseRow
    from vyuha.models.scoring import Verdict

    async def fetch_results_by_tag(tag: str) -> dict[str, str]:
        q = (
            select(RunRow.test_case_id, RunRow.verdict)
            .join(TestCaseRow, RunRow.test_case_id == TestCaseRow.id)
            .where(TestCaseRow.tags.contains([tag]))
        )
        result = await db.execute(q)
        return {row.test_case_id: row.verdict for row in result}

    baseline = await fetch_results_by_tag(baseline_tag)
    current = await fetch_results_by_tag(current_tag)

    newly_failed = [
        tid for tid in current
        if current[tid] == Verdict.FAIL and baseline.get(tid) == Verdict.PASS
    ]
    newly_passed = [
        tid for tid in current
        if current[tid] == Verdict.PASS and baseline.get(tid) == Verdict.FAIL
    ]
    return {
        "baseline_tag": baseline_tag,
        "current_tag": current_tag,
        "newly_failed": newly_failed,
        "newly_passed": newly_passed,
        "regression_count": len(newly_failed),
    }


@router.get("/executive-scorecard")
async def executive_scorecard(db: DbDep) -> dict[str, Any]:
    repo = RunRepo(db)
    stats = await repo.summary_stats()
    critical = await repo.count_critical_failures()
    rca = await repo.rca_breakdown()

    pass_rate = stats.get("pass_rate", 0.0)
    avg_eva_a = stats.get("avg_eva_a", 0.0)
    quality_score = round((pass_rate * 0.6 + avg_eva_a * 0.4) * 100, 1)

    return {
        "overall_quality_score": quality_score,
        "pass_rate_pct": round(pass_rate * 100, 1),
        "critical_failures": critical,
        "top_3_rca_codes": rca.get("breakdown", [])[:3],
        "total_runs_evaluated": stats.get("total_runs", 0),
        "avg_latency_p95_ms": stats.get("avg_latency_p95_ms", 0),
    }
