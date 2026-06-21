"""
/datasets — Dataset management (FutureAGI-parity).
Upload CSV/JSON/JSONL, manage rows, use in experiments.
"""
from __future__ import annotations
import csv, io, json, uuid
from typing import Annotated, Any
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, update

from vyuha.db import get_db
from vyuha.db.tables import DatasetRow, DatasetItemRow

log = structlog.get_logger()
router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


class DatasetCreate(BaseModel):
    name: str
    description: str = ""
    source: str = "build"


class RowsAdd(BaseModel):
    rows: list[dict[str, Any]]


@router.get("/")
async def list_datasets(db: DbDep):
    result = await db.execute(select(DatasetRow).order_by(DatasetRow.created_at.desc()))
    datasets = result.scalars().all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "source": d.source,
            "row_count": d.row_count,
            "created_at": d.created_at,
        }
        for d in datasets
    ]


@router.post("/")
async def create_dataset(body: DatasetCreate, db: DbDep):
    ds = DatasetRow(
        id=str(uuid.uuid4())[:8].upper(),
        name=body.name,
        description=body.description,
        source=body.source,
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, db: DbDep):
    result = await db.execute(select(DatasetRow).where(DatasetRow.id == dataset_id))
    ds = result.scalar_one_or_none()
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    items_result = await db.execute(
        select(DatasetItemRow)
        .where(DatasetItemRow.dataset_id == dataset_id)
        .order_by(DatasetItemRow.row_index)
        .limit(100)
    )
    items = items_result.scalars().all()
    return {
        "id": ds.id,
        "name": ds.name,
        "description": ds.description,
        "source": ds.source,
        "row_count": ds.row_count,
        "created_at": ds.created_at,
        "rows": [{"id": i.id, "row_index": i.row_index, "data": i.data} for i in items],
    }


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str, db: DbDep):
    result = await db.execute(select(DatasetRow).where(DatasetRow.id == dataset_id))
    ds = result.scalar_one_or_none()
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    await db.delete(ds)
    await db.commit()
    return {"deleted": dataset_id}


@router.post("/{dataset_id}/rows")
async def add_rows(dataset_id: str, body: RowsAdd, db: DbDep):
    result = await db.execute(select(DatasetRow).where(DatasetRow.id == dataset_id))
    ds = result.scalar_one_or_none()
    if ds is None:
        raise HTTPException(404, "Dataset not found")

    # Get current max row_index
    max_result = await db.execute(
        select(func.max(DatasetItemRow.row_index)).where(DatasetItemRow.dataset_id == dataset_id)
    )
    max_idx = max_result.scalar() or -1

    for i, row_data in enumerate(body.rows):
        item = DatasetItemRow(
            dataset_id=dataset_id,
            row_index=max_idx + 1 + i,
            data=row_data,
        )
        db.add(item)

    ds.row_count = ds.row_count + len(body.rows)
    await db.commit()
    await db.refresh(ds)
    return {"added": len(body.rows), "row_count": ds.row_count}


@router.delete("/{dataset_id}/rows/{row_id}")
async def delete_row(dataset_id: str, row_id: str, db: DbDep):
    result = await db.execute(
        select(DatasetItemRow).where(
            DatasetItemRow.id == row_id,
            DatasetItemRow.dataset_id == dataset_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Row not found")
    await db.delete(item)

    # Update row count
    ds_result = await db.execute(select(DatasetRow).where(DatasetRow.id == dataset_id))
    ds = ds_result.scalar_one_or_none()
    if ds and ds.row_count > 0:
        ds.row_count -= 1

    await db.commit()
    return {"deleted": row_id}


@router.get("/{dataset_id}/export")
async def export_dataset(dataset_id: str, db: DbDep):
    result = await db.execute(select(DatasetRow).where(DatasetRow.id == dataset_id))
    ds = result.scalar_one_or_none()
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    items_result = await db.execute(
        select(DatasetItemRow)
        .where(DatasetItemRow.dataset_id == dataset_id)
        .order_by(DatasetItemRow.row_index)
    )
    items = items_result.scalars().all()
    return {"dataset_id": dataset_id, "rows": [i.data for i in items]}


@router.post("/upload")
async def upload_dataset(
    db: DbDep,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(""),
):
    content = await file.read()
    filename = file.filename or ""
    content_type = file.content_type or ""

    rows: list[dict[str, Any]] = []

    if "csv" in content_type or filename.endswith(".csv"):
        text = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(r) for r in reader]
    elif "jsonl" in content_type or filename.endswith(".jsonl"):
        for line in content.decode("utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    else:
        # Assume JSON
        parsed = json.loads(content.decode("utf-8"))
        if not isinstance(parsed, list):
            raise HTTPException(400, "JSON file must be a list of objects")
        rows = parsed

    ds = DatasetRow(
        id=str(uuid.uuid4())[:8].upper(),
        name=name,
        description=description,
        source="upload",
        row_count=len(rows),
    )
    db.add(ds)
    await db.flush()

    for i, row_data in enumerate(rows):
        item = DatasetItemRow(dataset_id=ds.id, row_index=i, data=row_data)
        db.add(item)

    await db.commit()
    await db.refresh(ds)
    return {
        "id": ds.id,
        "name": ds.name,
        "row_count": ds.row_count,
        "source": ds.source,
        "created_at": ds.created_at,
    }
