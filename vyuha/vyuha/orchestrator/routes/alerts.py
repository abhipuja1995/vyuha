"""
/alerts — Alert monitors for evaluation metrics (FutureAGI-parity).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.db import get_db
from vyuha.db.tables import AlertMonitorRow, RunRow

log = structlog.get_logger()
router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


class MonitorCreate(BaseModel):
    name: str
    metric_type: str
    threshold_operator: str = "less_than"
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    check_interval_minutes: int = 60
    notification_emails: list[str] = []
    slack_webhook_url: str | None = None
    filters: dict[str, Any] = {}


class MonitorUpdate(BaseModel):
    name: str | None = None
    metric_type: str | None = None
    threshold_operator: str | None = None
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    check_interval_minutes: int | None = None
    notification_emails: list[str] | None = None
    slack_webhook_url: str | None = None
    filters: dict[str, Any] | None = None


def _compare(value: float, threshold: float, operator: str) -> bool:
    if operator == "less_than":
        return value < threshold
    elif operator == "greater_than":
        return value > threshold
    elif operator == "less_than_or_equal":
        return value <= threshold
    elif operator == "greater_than_or_equal":
        return value >= threshold
    return False


def _monitor_to_dict(m: AlertMonitorRow) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "metric_type": m.metric_type,
        "threshold_operator": m.threshold_operator,
        "warning_threshold": m.warning_threshold,
        "critical_threshold": m.critical_threshold,
        "check_interval_minutes": m.check_interval_minutes,
        "notification_emails": m.notification_emails,
        "slack_webhook_url": m.slack_webhook_url,
        "is_muted": m.is_muted,
        "filters": m.filters,
        "created_at": m.created_at,
    }


@router.get("/")
async def list_monitors(db: DbDep):
    result = await db.execute(select(AlertMonitorRow).order_by(AlertMonitorRow.created_at.desc()))
    return [_monitor_to_dict(m) for m in result.scalars().all()]


@router.post("/")
async def create_monitor(body: MonitorCreate, db: DbDep):
    m = AlertMonitorRow(
        id=str(uuid.uuid4())[:8],
        name=body.name,
        metric_type=body.metric_type,
        threshold_operator=body.threshold_operator,
        warning_threshold=body.warning_threshold,
        critical_threshold=body.critical_threshold,
        check_interval_minutes=body.check_interval_minutes,
        notification_emails=body.notification_emails,
        slack_webhook_url=body.slack_webhook_url,
        filters=body.filters,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _monitor_to_dict(m)


@router.get("/{monitor_id}")
async def get_monitor(monitor_id: str, db: DbDep):
    result = await db.execute(select(AlertMonitorRow).where(AlertMonitorRow.id == monitor_id))
    m = result.scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Monitor not found")
    return _monitor_to_dict(m)


@router.put("/{monitor_id}")
async def update_monitor(monitor_id: str, body: MonitorUpdate, db: DbDep):
    result = await db.execute(select(AlertMonitorRow).where(AlertMonitorRow.id == monitor_id))
    m = result.scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Monitor not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(m, field, val)
    await db.commit()
    await db.refresh(m)
    return _monitor_to_dict(m)


@router.delete("/{monitor_id}")
async def delete_monitor(monitor_id: str, db: DbDep):
    result = await db.execute(select(AlertMonitorRow).where(AlertMonitorRow.id == monitor_id))
    m = result.scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Monitor not found")
    await db.delete(m)
    await db.commit()
    return {"deleted": monitor_id}


@router.post("/{monitor_id}/mute")
async def toggle_mute(monitor_id: str, db: DbDep):
    result = await db.execute(select(AlertMonitorRow).where(AlertMonitorRow.id == monitor_id))
    m = result.scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Monitor not found")
    m.is_muted = not m.is_muted
    await db.commit()
    return {"is_muted": m.is_muted}


@router.post("/{monitor_id}/check")
async def check_monitor(monitor_id: str, db: DbDep):
    result = await db.execute(select(AlertMonitorRow).where(AlertMonitorRow.id == monitor_id))
    m = result.scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Monitor not found")

    current_value: float = 0.0

    if m.metric_type in ("pass_rate", "error_rate"):
        runs_result = await db.execute(
            select(RunRow).order_by(RunRow.started_at.desc()).limit(100)
        )
        runs = runs_result.scalars().all()
        if runs:
            total = len(runs)
            passed = sum(1 for r in runs if r.verdict == "PASS")
            pass_rate = passed / total
            current_value = pass_rate if m.metric_type == "pass_rate" else 1.0 - pass_rate
        else:
            current_value = 0.0
    elif m.metric_type == "latency":
        lat_result = await db.execute(
            select(func.avg(RunRow.latency_p95_ms)).where(RunRow.latency_p95_ms.isnot(None))
        )
        current_value = lat_result.scalar() or 0.0

    # Determine status
    status = "ok"
    if m.critical_threshold is not None and _compare(current_value, m.critical_threshold, m.threshold_operator):
        status = "critical"
    elif m.warning_threshold is not None and _compare(current_value, m.warning_threshold, m.threshold_operator):
        status = "warning"

    return {
        "status": status,
        "current_value": current_value,
        "warning_threshold": m.warning_threshold,
        "critical_threshold": m.critical_threshold,
        "metric_type": m.metric_type,
        "checked_at": datetime.now(timezone.utc),
    }
