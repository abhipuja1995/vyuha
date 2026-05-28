from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.db import TestCaseRepo, RunRepo, PassKRepo, get_db
from vyuha.models.scoring import RunResult, PassKResult

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]


class RunRequest(BaseModel):
    test_id: str
    vaut_url: str | None = None
    mode: str = "text"
    k: int = 1
    seed: int | None = None


@router.post("/")
async def start_run(req: RunRequest, db: DbDep) -> dict:
    tc = await TestCaseRepo(db).get(req.test_id)
    if not tc:
        raise HTTPException(status_code=404, detail=f"Test case {req.test_id} not found")

    from vyuha.workers.tasks import run_test_case

    task_ids = []
    for _ in range(req.k):
        task = run_test_case.delay(
            test_id=req.test_id,
            vaut_url=req.vaut_url,
            mode=req.mode,
            seed=req.seed,
        )
        task_ids.append(task.id)

    return {
        "message": "Run(s) queued",
        "test_id": req.test_id,
        "k": req.k,
        "task_ids": task_ids,
    }


@router.get("/task/{task_id}")
async def get_task_status(task_id: str) -> dict:
    """Check Celery task status."""
    from vyuha.workers.celery_app import app
    result = app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }


@router.get("/{run_id}", response_model=RunResult)
async def get_run(run_id: str, db: DbDep) -> RunResult:
    run = await RunRepo(db).get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@router.get("/for-test/{test_id}", response_model=list[RunResult])
async def list_runs_for_test(test_id: str, db: DbDep, limit: int = 20) -> list[RunResult]:
    return await RunRepo(db).list_for_test(test_id, limit=limit)
