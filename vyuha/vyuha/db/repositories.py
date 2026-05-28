"""
Repository layer: converts between SQLAlchemy ORM rows and Pydantic domain models.
All DB access in the application goes through these classes.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.db.tables import TestCaseRow, RunRow, PassKRow
from vyuha.models.test_case import (
    TestCase, PersonaConfig, ConversationGraph, ToolCallSpec,
    TestCategory, Language,
)
from vyuha.models.scoring import (
    RunResult, EvaAScore, EvaXScore, DiagnosticMetrics, FailureReport,
    PassKResult, Verdict,
)
from vyuha.models.rca import RCATag, RCACode


# ─── TestCase Repository ──────────────────────────────────────────────────────

class TestCaseRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save(self, tc: TestCase) -> TestCase:
        row = TestCaseRow(
            id=tc.test_id,
            title=tc.title,
            category=tc.category.value,
            user_goal=tc.user_goal,
            pass_criteria=tc.pass_criteria,
            created_by=tc.created_by,
            version=tc.version,
            linked_production_call=tc.linked_production_call,
            persona_config=tc.persona_config.model_dump(mode="json"),
            conversation_graph=tc.conversation_graph.model_dump(mode="json"),
            tool_call_sequence=[t.model_dump(mode="json") for t in tc.tool_call_sequence],
            ground_truth_end_state=tc.ground_truth_end_state,
            tags=tc.tags,
        )
        self.db.add(row)
        await self.db.commit()
        return tc

    async def get(self, test_id: str) -> TestCase | None:
        row = await self.db.get(TestCaseRow, test_id)
        return _row_to_test_case(row) if row else None

    async def list(
        self,
        category: TestCategory | None = None,
        language: Language | None = None,
        tag: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[TestCase]:
        q = select(TestCaseRow)
        if category:
            q = q.where(TestCaseRow.category == category.value)
        if language:
            q = q.where(TestCaseRow.persona_config["language"].astext == language.value)
        if tag:
            q = q.where(TestCaseRow.tags.contains([tag]))
        q = q.order_by(desc(TestCaseRow.created_at)).limit(limit).offset(offset)
        result = await self.db.execute(q)
        return [_row_to_test_case(r) for r in result.scalars()]

    async def delete(self, test_id: str) -> bool:
        row = await self.db.get(TestCaseRow, test_id)
        if not row:
            return False
        await self.db.delete(row)
        await self.db.commit()
        return True

    async def count(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(TestCaseRow))
        return result.scalar_one()

    async def patch_node_audio(self, test_id: str, node_id: str, audio_file: str | None) -> bool:
        """Update a single node's audio_file field within the conversation_graph JSONB."""
        from sqlalchemy.orm.attributes import flag_modified
        row = await self.db.get(TestCaseRow, test_id)
        if not row:
            return False
        graph: dict = dict(row.conversation_graph)
        nodes = graph.get("nodes", [])
        updated = False
        for node in nodes:
            if node.get("node_id") == node_id:
                node["audio_file"] = audio_file
                updated = True
                break
        if not updated:
            return False
        row.conversation_graph = graph
        flag_modified(row, "conversation_graph")
        await self.db.commit()
        return True


def _row_to_test_case(row: TestCaseRow) -> TestCase:
    return TestCase(
        test_id=row.id,
        title=row.title,
        category=TestCategory(row.category),
        user_goal=row.user_goal,
        pass_criteria=row.pass_criteria,
        created_by=row.created_by,
        version=row.version,
        linked_production_call=row.linked_production_call,
        persona_config=PersonaConfig(**row.persona_config),
        conversation_graph=ConversationGraph(**row.conversation_graph),
        tool_call_sequence=[ToolCallSpec(**t) for t in row.tool_call_sequence],
        ground_truth_end_state=row.ground_truth_end_state,
        tags=row.tags,
        created_at=row.created_at,
    )


# ─── Run Repository ───────────────────────────────────────────────────────────

class RunRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save(self, run: RunResult) -> RunResult:
        row = RunRow(
            id=run.run_id,
            test_case_id=run.test_id,
            started_at=run.started_at,
            completed_at=run.completed_at,
            verdict=run.verdict.value,
            judge_model_used=run.judge_model_used,
            error_message=run.error_message,
            eva_a_task_completion=run.eva_a.task_completion,
            eva_a_faithfulness=run.eva_a.faithfulness,
            eva_a_speech_fidelity=run.eva_a.speech_fidelity,
            eva_a_composite=run.eva_a.composite,
            eva_x_conciseness=run.eva_x.conciseness,
            eva_x_progression=run.eva_x.conversation_progression,
            eva_x_turn_taking=run.eva_x.turn_taking,
            eva_x_composite=run.eva_x.composite,
            latency_p50_ms=run.diagnostics.latency_p50_ms,
            latency_p95_ms=run.diagnostics.latency_p95_ms,
            turns=[t.model_dump(mode="json") for t in run.turns],
            final_db_state=run.final_db_state,
            failure_report=run.failure_report.model_dump(mode="json") if run.failure_report else None,
        )
        self.db.add(row)
        await self.db.commit()
        return run

    async def get(self, run_id: str) -> RunResult | None:
        row = await self.db.get(RunRow, run_id)
        return _row_to_run_result(row) if row else None

    async def list_for_test(self, test_id: str, limit: int = 50) -> list[RunResult]:
        q = (
            select(RunRow)
            .where(RunRow.test_case_id == test_id)
            .order_by(desc(RunRow.started_at))
            .limit(limit)
        )
        result = await self.db.execute(q)
        return [_row_to_run_result(r) for r in result.scalars()]

    async def summary_stats(self) -> dict[str, Any]:
        """Aggregate stats across all runs for the summary report."""
        q = select(
            func.count().label("total"),
            func.sum((RunRow.verdict == "PASS").cast(int)).label("passed"),
            func.sum((RunRow.verdict == "FAIL").cast(int)).label("failed"),
            func.sum((RunRow.verdict == "ERROR").cast(int)).label("errors"),
            func.avg(RunRow.eva_a_composite).label("avg_eva_a"),
            func.avg(RunRow.eva_x_composite).label("avg_eva_x"),
            func.avg(RunRow.latency_p95_ms).label("avg_p95_ms"),
        ).select_from(RunRow)
        result = await self.db.execute(q)
        row = result.one()
        total = row.total or 0
        passed = row.passed or 0
        return {
            "total_runs": total,
            "passed": passed,
            "failed": row.failed or 0,
            "errors": row.errors or 0,
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "avg_eva_a": round(float(row.avg_eva_a or 0), 4),
            "avg_eva_x": round(float(row.avg_eva_x or 0), 4),
            "avg_latency_p95_ms": round(float(row.avg_p95_ms or 0), 1),
        }

    async def rca_breakdown(self) -> dict[str, Any]:
        """Pull all failure_report JSONB, extract RCA codes, aggregate."""
        q = select(RunRow.failure_report).where(RunRow.failure_report.is_not(None))
        result = await self.db.execute(q)
        from collections import Counter
        counts: Counter[str] = Counter()
        for (report,) in result:
            for tag in (report or {}).get("rca_tags", []):
                counts[tag["code"]] += 1
        total = sum(counts.values())
        breakdown = [
            {"rca_code": c, "count": n, "percentage": round(n / total * 100, 1) if total else 0}
            for c, n in counts.most_common()
        ]
        return {"total_failure_tags": total, "breakdown": breakdown}

    async def count_critical_failures(self) -> int:
        q = select(func.count()).select_from(RunRow).where(RunRow.failure_report.is_not(None))
        result = await self.db.execute(q)
        # Count rows where any rca_tag has code == RCA-SAFE-01
        # For simplicity at Phase 2, query and filter in Python
        all_q = select(RunRow.failure_report).where(RunRow.failure_report.is_not(None))
        all_result = await self.db.execute(all_q)
        count = 0
        for (report,) in all_result:
            if any(t.get("code") == "RCA-SAFE-01" for t in (report or {}).get("rca_tags", [])):
                count += 1
        return count


def _row_to_run_result(row: RunRow) -> RunResult:
    from vyuha.models.scoring import TurnResult
    from datetime import datetime

    eva_a = EvaAScore(
        task_completion=row.eva_a_task_completion or 0.0,
        faithfulness=row.eva_a_faithfulness or 0.0,
        speech_fidelity=row.eva_a_speech_fidelity or 0.0,
    )
    eva_x = EvaXScore(
        conciseness=row.eva_x_conciseness or 0.0,
        conversation_progression=row.eva_x_progression or 0.0,
        turn_taking=row.eva_x_turn_taking or 0.0,
    )
    diagnostics = DiagnosticMetrics(
        latency_p50_ms=row.latency_p50_ms or 0.0,
        latency_p95_ms=row.latency_p95_ms or 0.0,
    )
    failure_report = None
    if row.failure_report:
        fr = row.failure_report
        rca_tags = [
            RCATag.from_code(RCACode(t["code"]), t.get("turn_index"), float(t.get("confidence", 1.0)))
            for t in fr.get("rca_tags", [])
        ]
        failure_report = FailureReport(
            eva_a_score=eva_a,
            eva_x_score=eva_x,
            failed_criterion=fr.get("failed_criterion", ""),
            failure_turn_index=fr.get("failure_turn_index", 0),
            failure_excerpt=fr.get("failure_excerpt", ""),
            rca_tags=rca_tags,
        )

    return RunResult(
        run_id=row.id,
        test_id=row.test_case_id,
        started_at=row.started_at,
        completed_at=row.completed_at or row.started_at,
        verdict=Verdict(row.verdict),
        eva_a=eva_a,
        eva_x=eva_x,
        diagnostics=diagnostics,
        turns=[TurnResult(**t) for t in row.turns],
        final_db_state=row.final_db_state,
        failure_report=failure_report,
        judge_model_used=row.judge_model_used,
        error_message=row.error_message,
    )


# ─── PassK Repository ────────────────────────────────────────────────────────

class PassKRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save(self, result: PassKResult) -> None:
        row = PassKRow(
            test_case_id=result.test_id,
            k=result.k,
            pass_at_k=result.pass_at_k,
            pass_all_k=result.pass_all_k,
            mean_eva_a=result.mean_eva_a,
            mean_eva_x=result.mean_eva_x,
            run_ids=[r.run_id for r in result.runs],
        )
        self.db.add(row)
        await self.db.commit()

    async def get_latest(self, test_id: str) -> PassKRow | None:
        q = (
            select(PassKRow)
            .where(PassKRow.test_case_id == test_id)
            .order_by(desc(PassKRow.created_at))
            .limit(1)
        )
        result = await self.db.execute(q)
        return result.scalar_one_or_none()
