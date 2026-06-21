"""
/traces — Observability: trace + span storage with OTLP ingest (FutureAGI-parity).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.db import get_db
from vyuha.db.tables import SpanRow, TraceRow

log = structlog.get_logger()
router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


class TraceCreate(BaseModel):
    name: str = ""
    session_id: str | None = None
    user_id: str | None = None
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    input: dict | None = None
    output: dict | None = None
    error: str | None = None


class SpanCreate(BaseModel):
    id: str | None = None
    parent_span_id: str | None = None
    span_kind: str = "llm"
    operation_name: str
    start_time: datetime
    end_time: datetime | None = None
    latency_ms: float | None = None
    input: dict | None = None
    output: dict | None = None
    model: str | None = None
    provider: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    status: str = "OK"
    tags: list[str] = []
    attributes: dict[str, Any] = {}


@router.post("/")
async def create_trace(body: TraceCreate, db: DbDep):
    trace = TraceRow(
        id=str(uuid.uuid4()),
        name=body.name,
        session_id=body.session_id,
        user_id=body.user_id,
        tags=body.tags,
        metadata_=body.metadata,
        input_=body.input,
        output=body.output,
        error=body.error,
    )
    db.add(trace)
    await db.commit()
    await db.refresh(trace)
    return {"id": trace.id, "name": trace.name, "created_at": trace.created_at}


@router.get("/")
async def list_traces(
    db: DbDep,
    session_id: str | None = Query(None),
    user_id: str | None = Query(None),
    limit: int = Query(50, le=500),
):
    q = select(TraceRow).order_by(TraceRow.created_at.desc()).limit(limit)
    if session_id:
        q = q.where(TraceRow.session_id == session_id)
    if user_id:
        q = q.where(TraceRow.user_id == user_id)
    result = await db.execute(q)
    traces = result.scalars().all()

    out = []
    for t in traces:
        cnt_result = await db.execute(select(func.count()).where(SpanRow.trace_id == t.id))
        span_count = cnt_result.scalar() or 0
        out.append({
            "id": t.id,
            "name": t.name,
            "session_id": t.session_id,
            "user_id": t.user_id,
            "tags": t.tags,
            "error": t.error,
            "span_count": span_count,
            "created_at": t.created_at,
        })
    return out


@router.get("/sessions")
async def list_sessions(db: DbDep):
    result = await db.execute(
        select(TraceRow.session_id, func.count(TraceRow.id).label("trace_count"))
        .where(TraceRow.session_id.isnot(None))
        .group_by(TraceRow.session_id)
        .order_by(func.count(TraceRow.id).desc())
    )
    rows = result.all()
    return [{"session_id": r.session_id, "trace_count": r.trace_count} for r in rows]


@router.get("/stats")
async def get_stats(db: DbDep):
    total_traces_result = await db.execute(select(func.count(TraceRow.id)))
    total_traces = total_traces_result.scalar() or 0

    total_spans_result = await db.execute(select(func.count(SpanRow.id)))
    total_spans = total_spans_result.scalar() or 0

    avg_lat_result = await db.execute(select(func.avg(SpanRow.latency_ms)))
    avg_latency_ms = avg_lat_result.scalar()

    total_tokens_result = await db.execute(select(func.sum(SpanRow.total_tokens)))
    total_tokens = total_tokens_result.scalar()

    total_cost_result = await db.execute(select(func.sum(SpanRow.cost_usd)))
    total_cost_usd = total_cost_result.scalar()

    return {
        "total_traces": total_traces,
        "total_spans": total_spans,
        "avg_latency_ms": avg_latency_ms,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost_usd,
    }


@router.get("/{trace_id}")
async def get_trace(trace_id: str, db: DbDep):
    result = await db.execute(select(TraceRow).where(TraceRow.id == trace_id))
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(404, "Trace not found")
    spans_result = await db.execute(
        select(SpanRow).where(SpanRow.trace_id == trace_id).order_by(SpanRow.start_time)
    )
    spans = spans_result.scalars().all()
    return {
        "id": trace.id,
        "name": trace.name,
        "session_id": trace.session_id,
        "user_id": trace.user_id,
        "tags": trace.tags,
        "metadata": trace.metadata_,
        "input": trace.input_,
        "output": trace.output,
        "error": trace.error,
        "created_at": trace.created_at,
        "spans": [_span_to_dict(s) for s in spans],
    }


@router.delete("/{trace_id}")
async def delete_trace(trace_id: str, db: DbDep):
    result = await db.execute(select(TraceRow).where(TraceRow.id == trace_id))
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(404, "Trace not found")
    await db.delete(trace)
    await db.commit()
    return {"deleted": trace_id}


@router.post("/{trace_id}/spans")
async def create_span(trace_id: str, body: SpanCreate, db: DbDep):
    result = await db.execute(select(TraceRow).where(TraceRow.id == trace_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Trace not found")

    latency_ms = body.latency_ms
    if latency_ms is None and body.end_time and body.start_time:
        latency_ms = (body.end_time - body.start_time).total_seconds() * 1000

    span = SpanRow(
        id=body.id or str(uuid.uuid4()),
        trace_id=trace_id,
        parent_span_id=body.parent_span_id,
        span_kind=body.span_kind,
        operation_name=body.operation_name,
        start_time=body.start_time,
        end_time=body.end_time,
        latency_ms=latency_ms,
        input_=body.input,
        output=body.output,
        model=body.model,
        provider=body.provider,
        prompt_tokens=body.prompt_tokens,
        completion_tokens=body.completion_tokens,
        total_tokens=body.total_tokens,
        cost_usd=body.cost_usd,
        status=body.status,
        tags=body.tags,
        attributes=body.attributes,
    )
    db.add(span)
    await db.commit()
    await db.refresh(span)
    return _span_to_dict(span)


@router.get("/{trace_id}/spans")
async def list_spans(trace_id: str, db: DbDep):
    result = await db.execute(select(TraceRow).where(TraceRow.id == trace_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Trace not found")
    spans_result = await db.execute(
        select(SpanRow).where(SpanRow.trace_id == trace_id).order_by(SpanRow.start_time)
    )
    return [_span_to_dict(s) for s in spans_result.scalars().all()]


@router.post("/ingest/otlp")
async def ingest_otlp(body: dict, db: DbDep):
    """Ingest OpenTelemetry OTLP JSON format."""
    created_spans = 0
    created_traces = 0

    _OTEL_KIND_MAP = {0: "internal", 1: "server", 2: "chain", 3: "llm", 4: "producer", 5: "consumer"}

    trace_cache: dict[str, str] = {}  # otel_trace_id -> our trace row id

    for resource_span in body.get("resourceSpans", []):
        for scope_span in resource_span.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                otel_trace_id = span.get("traceId", "")

                if otel_trace_id not in trace_cache:
                    # Check if trace already exists by name
                    existing = await db.execute(
                        select(TraceRow).where(TraceRow.name == otel_trace_id).limit(1)
                    )
                    existing_trace = existing.scalar_one_or_none()
                    if existing_trace:
                        trace_cache[otel_trace_id] = existing_trace.id
                    else:
                        new_trace = TraceRow(id=str(uuid.uuid4()), name=otel_trace_id)
                        db.add(new_trace)
                        await db.flush()
                        trace_cache[otel_trace_id] = new_trace.id
                        created_traces += 1

                trace_row_id = trace_cache[otel_trace_id]

                start_ns = int(span.get("startTimeUnixNano", 0))
                end_ns = int(span.get("endTimeUnixNano", 0))
                start_dt = datetime.fromtimestamp(start_ns / 1e9, tz=timezone.utc) if start_ns else datetime.now(timezone.utc)
                end_dt = datetime.fromtimestamp(end_ns / 1e9, tz=timezone.utc) if end_ns else None
                latency_ms = (end_ns - start_ns) / 1e6 if end_ns and start_ns else None

                otel_kind = span.get("kind", 0)
                span_kind = _OTEL_KIND_MAP.get(otel_kind, "llm")

                otel_span_row = SpanRow(
                    id=span.get("spanId", str(uuid.uuid4())),
                    trace_id=trace_row_id,
                    parent_span_id=span.get("parentSpanId") or None,
                    span_kind=span_kind,
                    operation_name=span.get("name", ""),
                    start_time=start_dt,
                    end_time=end_dt,
                    latency_ms=latency_ms,
                    status=span.get("status", {}).get("code", "OK"),
                    status_message=span.get("status", {}).get("message"),
                    attributes={a["key"]: a.get("value", {}) for a in span.get("attributes", [])},
                )
                db.add(otel_span_row)
                created_spans += 1

    await db.commit()
    return {"created_traces": created_traces, "created_spans": created_spans}


def _span_to_dict(s: SpanRow) -> dict:
    return {
        "id": s.id,
        "trace_id": s.trace_id,
        "parent_span_id": s.parent_span_id,
        "span_kind": s.span_kind,
        "operation_name": s.operation_name,
        "start_time": s.start_time,
        "end_time": s.end_time,
        "latency_ms": s.latency_ms,
        "input": s.input_,
        "output": s.output,
        "model": s.model,
        "provider": s.provider,
        "prompt_tokens": s.prompt_tokens,
        "completion_tokens": s.completion_tokens,
        "total_tokens": s.total_tokens,
        "cost_usd": s.cost_usd,
        "status": s.status,
        "tags": s.tags,
        "attributes": s.attributes,
    }
