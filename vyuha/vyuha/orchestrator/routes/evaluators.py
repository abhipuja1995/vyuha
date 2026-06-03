"""
/evaluators — Portable eval library API (FutureAGI-inspired).

  GET  /evaluators                    list all 30+ available evaluators
  POST /evaluators/run                run a single evaluator on one row
  POST /evaluators/run/batch          run over a list of rows
  POST /evaluators/experiment         run multiple evals over a dataset, save results
  GET  /evaluators/experiments        list past experiments
  GET  /evaluators/experiments/{id}   get experiment results
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from vyuha.db import get_db
from vyuha.db.tables import Base
from vyuha.evaluators.registry import EvalRegistry

log = structlog.get_logger()
router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


# ── In-memory experiment store (persisted to DB when available) ───────────────
# For now a simple dict; in prod this would be its own DB table.
_experiments: dict[str, dict[str, Any]] = {}


# ── Request/Response models ───────────────────────────────────────────────────

class EvalRunRequest(BaseModel):
    evaluator: str                          # e.g. "rouge_score", "contains_any"
    inputs: dict[str, Any] = {}            # e.g. {"output": "...", "expected": "..."}
    config: dict[str, Any] = {}            # constructor kwargs, e.g. {"k": 3}
    # LLM step — if set, system calls LLM(user_input) → output, then evaluates
    user_input: str | None = None          # if provided, LLM generates output first
    system_prompt: str = ""               # optional system prompt for LLM call
    expected: str | None = None           # expected output for comparison


class EvalBatchRequest(BaseModel):
    evaluator: str
    rows: list[dict[str, Any]]              # each row = inputs dict
    config: dict[str, Any] = {}
    max_parallel: int = 8
    # LLM step for each row
    system_prompt: str = ""               # applied to all rows if user_input key present


class ExperimentRequest(BaseModel):
    name: str
    evaluators: list[dict[str, Any]]        # [{"name": "rouge_score", "config": {...}}]
    dataset: list[dict[str, Any]]           # rows with "output", "expected", etc.
    description: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def list_evaluators() -> list[dict[str, Any]]:
    """Return all registered evaluators with name, description, required_keys."""
    return EvalRegistry.list_all()


@router.get("/active-llm")
async def get_active_llm() -> dict[str, Any]:
    """Return the best currently configured LLM provider."""
    from vyuha.utils.llm_router import active_provider
    p = active_provider()
    return {"provider": p, "configured": p != "none"}


@router.post("/run")
async def run_evaluator(req: EvalRunRequest) -> dict[str, Any]:
    """
    Run a single evaluator.
    If user_input is provided, the best available LLM generates output first,
    then the evaluator scores it against expected. This is the correct flow:
      user_input → [LLM] → output → [evaluator] → score
    """
    cls = EvalRegistry.get(req.evaluator)
    if cls is None:
        raise HTTPException(404, f"Unknown evaluator '{req.evaluator}'. GET /evaluators for list.")

    inputs = dict(req.inputs)
    llm_output: str | None = None
    provider_used: str | None = None

    # LLM step: if user_input given, generate output first
    if req.user_input:
        try:
            from vyuha.utils.llm_router import call as llm_call, active_provider
            llm_resp = await llm_call(req.user_input, system=req.system_prompt)
            llm_output = llm_resp.text
            provider_used = llm_resp.provider
            inputs["output"] = llm_output
            if req.expected is not None:
                inputs["expected"] = req.expected
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))

    try:
        instance = cls(**req.config) if req.config else cls()
        result = instance.run(**inputs)
        response = {"evaluator": req.evaluator, **result.to_dict()}
        if llm_output is not None:
            response["llm_output"] = llm_output
            response["llm_provider"] = provider_used
            response["user_input"] = req.user_input
        return response
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/run/batch")
async def run_evaluator_batch(req: EvalBatchRequest) -> dict[str, Any]:
    """
    Run an evaluator over a list of rows.
    If a row has 'user_input', LLM generates output first then evaluates.
    """
    cls = EvalRegistry.get(req.evaluator)
    if cls is None:
        raise HTTPException(404, f"Unknown evaluator '{req.evaluator}'.")

    # LLM step for rows that have user_input
    rows = list(req.rows)
    provider_used: str | None = None
    rows_with_llm = [i for i, r in enumerate(rows) if "user_input" in r]
    if rows_with_llm:
        try:
            from vyuha.utils.llm_router import call as llm_call
            import asyncio
            async def _gen(row):
                resp = await llm_call(row["user_input"], system=req.system_prompt)
                return resp.text, resp.provider
            outputs = await asyncio.gather(*[_gen(rows[i]) for i in rows_with_llm])
            for idx, (text, prov) in zip(rows_with_llm, outputs):
                rows[idx] = {**rows[idx], "output": text}
                provider_used = prov
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))

    try:
        instance = cls(**req.config) if req.config else cls()
        results = instance.run_batch(rows, max_parallel=req.max_parallel)
        rows_out = [r.to_dict() for r in results]
        values = [r.value for r in results if isinstance(r.value, (int, float))]
        passed = sum(1 for r in results if r.passed is True)
        return {
            "evaluator": req.evaluator,
            "total": len(results),
            "passed": passed,
            "failed": len([r for r in results if r.passed is False]),
            "avg_value": round(sum(values) / len(values), 4) if values else None,
            **({"llm_provider": provider_used} if provider_used else {}),
            "results": rows_out,
        }
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/experiment")
async def run_experiment(req: ExperimentRequest) -> dict[str, Any]:
    """
    Run multiple evaluators over a dataset.
    Returns aggregated metrics per evaluator + per-row results.
    Stores experiment in memory (accessible via GET /evaluators/experiments/{id}).
    """
    exp_id = str(uuid.uuid4())[:8].upper()
    started_at = datetime.now(timezone.utc)

    eval_results: dict[str, Any] = {}

    for eval_cfg in req.evaluators:
        eval_name = eval_cfg.get("name", "")
        config = eval_cfg.get("config", {})
        cls = EvalRegistry.get(eval_name)
        if cls is None:
            eval_results[eval_name] = {"error": f"Unknown evaluator '{eval_name}'"}
            continue
        try:
            instance = cls(**config) if config else cls()
            row_results = instance.run_batch(req.dataset)
            row_dicts = [r.to_dict() for r in row_results]
            values = [r.value for r in row_results if isinstance(r.value, (int, float))]
            passed = sum(1 for r in row_results if r.passed is True)
            eval_results[eval_name] = {
                "total": len(row_results),
                "passed": passed,
                "failed": len([r for r in row_results if r.passed is False]),
                "avg_value": round(sum(values) / len(values), 4) if values else None,
                "rows": row_dicts,
            }
        except Exception as exc:
            eval_results[eval_name] = {"error": str(exc)}
            log.warning("experiment_eval_failed", eval_name=eval_name, error=str(exc))

    completed_at = datetime.now(timezone.utc)
    experiment = {
        "id": exp_id,
        "name": req.name,
        "description": req.description,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": round((completed_at - started_at).total_seconds() * 1000),
        "dataset_size": len(req.dataset),
        "evaluators": [e.get("name") for e in req.evaluators],
        "results": eval_results,
    }
    _experiments[exp_id] = experiment
    log.info("experiment_complete", exp_id=exp_id, name=req.name, evals=len(req.evaluators))
    return experiment


@router.get("/experiments")
async def list_experiments() -> list[dict[str, Any]]:
    """List all experiments (summary, no per-row details)."""
    return [
        {k: v for k, v in exp.items() if k != "results"}
        | {"evaluator_summaries": {
            name: {k: v for k, v in data.items() if k != "rows"}
            for name, data in exp.get("results", {}).items()
        }}
        for exp in sorted(_experiments.values(), key=lambda e: e["started_at"], reverse=True)
    ]


@router.get("/experiments/{exp_id}")
async def get_experiment(exp_id: str) -> dict[str, Any]:
    """Get full experiment result including per-row scores."""
    exp = _experiments.get(exp_id.upper())
    if not exp:
        raise HTTPException(404, f"Experiment {exp_id} not found.")
    return exp
