"""
/annotations — Human annotation queues for labeling test cases and runs (FutureAGI-parity).
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
from vyuha.db.tables import AnnotationItemRow, AnnotationQueueRow

log = structlog.get_logger()
router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


class QueueCreate(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    labels: list[dict[str, Any]] = []
    annotations_required: int = 1


class QueueUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    status: str | None = None
    labels: list[dict[str, Any]] | None = None


class ItemCreate(BaseModel):
    source_type: str
    source_id: str


class AnnotateRequest(BaseModel):
    label: str
    value: Any
    annotator: str = "anonymous"
    notes: str = ""


@router.get("/queues")
async def list_queues(db: DbDep):
    result = await db.execute(select(AnnotationQueueRow).order_by(AnnotationQueueRow.created_at.desc()))
    queues = result.scalars().all()
    out = []
    for q in queues:
        cnt_result = await db.execute(select(func.count()).where(AnnotationItemRow.queue_id == q.id))
        item_count = cnt_result.scalar() or 0
        out.append({
            "id": q.id,
            "name": q.name,
            "status": q.status,
            "item_count": item_count,
            "annotations_required": q.annotations_required,
            "created_at": q.created_at,
        })
    return out


@router.post("/queues")
async def create_queue(body: QueueCreate, db: DbDep):
    q = AnnotationQueueRow(
        id=str(uuid.uuid4())[:8],
        name=body.name,
        description=body.description,
        instructions=body.instructions,
        labels=body.labels,
        annotations_required=body.annotations_required,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return _queue_to_dict(q)


@router.get("/queues/{queue_id}")
async def get_queue(queue_id: str, db: DbDep):
    result = await db.execute(select(AnnotationQueueRow).where(AnnotationQueueRow.id == queue_id))
    q = result.scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "Queue not found")
    items_result = await db.execute(
        select(AnnotationItemRow).where(AnnotationItemRow.queue_id == queue_id).order_by(AnnotationItemRow.created_at)
    )
    items = items_result.scalars().all()
    return {
        **_queue_to_dict(q),
        "items": [_item_to_dict(i) for i in items],
    }


@router.put("/queues/{queue_id}")
async def update_queue(queue_id: str, body: QueueUpdate, db: DbDep):
    result = await db.execute(select(AnnotationQueueRow).where(AnnotationQueueRow.id == queue_id))
    q = result.scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "Queue not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(q, field, val)
    await db.commit()
    await db.refresh(q)
    return _queue_to_dict(q)


@router.delete("/queues/{queue_id}")
async def delete_queue(queue_id: str, db: DbDep):
    result = await db.execute(select(AnnotationQueueRow).where(AnnotationQueueRow.id == queue_id))
    q = result.scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "Queue not found")
    await db.delete(q)
    await db.commit()
    return {"deleted": queue_id}


@router.post("/queues/{queue_id}/items")
async def add_item(queue_id: str, body: ItemCreate, db: DbDep):
    result = await db.execute(select(AnnotationQueueRow).where(AnnotationQueueRow.id == queue_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Queue not found")
    item = AnnotationItemRow(
        id=str(uuid.uuid4()),
        queue_id=queue_id,
        source_type=body.source_type,
        source_id=body.source_id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _item_to_dict(item)


@router.get("/queues/{queue_id}/items/{item_id}")
async def get_item(queue_id: str, item_id: str, db: DbDep):
    result = await db.execute(
        select(AnnotationItemRow).where(
            AnnotationItemRow.id == item_id,
            AnnotationItemRow.queue_id == queue_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Item not found")
    return _item_to_dict(item)


@router.post("/queues/{queue_id}/items/{item_id}/annotate")
async def annotate_item(queue_id: str, item_id: str, body: AnnotateRequest, db: DbDep):
    # Get queue for annotations_required
    q_result = await db.execute(select(AnnotationQueueRow).where(AnnotationQueueRow.id == queue_id))
    q = q_result.scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "Queue not found")

    result = await db.execute(
        select(AnnotationItemRow).where(
            AnnotationItemRow.id == item_id,
            AnnotationItemRow.queue_id == queue_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Item not found")

    annotation = {
        "label": body.label,
        "value": body.value,
        "annotator": body.annotator,
        "notes": body.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    item.annotations = list(item.annotations) + [annotation]

    if len(item.annotations) >= q.annotations_required:
        item.status = "completed"

    await db.commit()
    await db.refresh(item)
    return _item_to_dict(item)


@router.get("/queues/{queue_id}/stats")
async def queue_stats(queue_id: str, db: DbDep):
    result = await db.execute(select(AnnotationQueueRow).where(AnnotationQueueRow.id == queue_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Queue not found")

    total_result = await db.execute(select(func.count()).where(AnnotationItemRow.queue_id == queue_id))
    total = total_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count()).where(AnnotationItemRow.queue_id == queue_id, AnnotationItemRow.status == "pending")
    )
    pending = pending_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count()).where(AnnotationItemRow.queue_id == queue_id, AnnotationItemRow.status == "completed")
    )
    completed = completed_result.scalar() or 0

    return {
        "total": total,
        "pending": pending,
        "completed": completed,
        "completion_rate": completed / total if total > 0 else 0.0,
    }


def _queue_to_dict(q: AnnotationQueueRow) -> dict:
    return {
        "id": q.id,
        "name": q.name,
        "description": q.description,
        "instructions": q.instructions,
        "status": q.status,
        "annotations_required": q.annotations_required,
        "labels": q.labels,
        "created_at": q.created_at,
    }


def _item_to_dict(i: AnnotationItemRow) -> dict:
    return {
        "id": i.id,
        "queue_id": i.queue_id,
        "source_type": i.source_type,
        "source_id": i.source_id,
        "status": i.status,
        "annotations": i.annotations,
        "created_at": i.created_at,
    }
