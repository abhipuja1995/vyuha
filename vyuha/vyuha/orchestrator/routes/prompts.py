"""
/prompts — Prompt template versioning and A/B comparison (FutureAGI-parity).
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
from vyuha.db.tables import PromptTemplateRow, PromptVersionRow

log = structlog.get_logger()
router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    folder: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    folder: str | None = None


class VersionCreate(BaseModel):
    messages: list[dict[str, Any]]
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    commit_message: str = ""
    label: str = "draft"


class VersionLabelUpdate(BaseModel):
    label: str


class RunRequest(BaseModel):
    variables: dict[str, Any] = {}


class CompareRequest(BaseModel):
    version_ids: list[str]
    input_variables: dict[str, Any] = {}


@router.get("/")
async def list_templates(db: DbDep):
    result = await db.execute(select(PromptTemplateRow).order_by(PromptTemplateRow.created_at.desc()))
    templates = result.scalars().all()
    out = []
    for t in templates:
        latest_result = await db.execute(
            select(PromptVersionRow)
            .where(PromptVersionRow.template_id == t.id)
            .order_by(PromptVersionRow.version_number.desc())
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()
        out.append({
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "folder": t.folder,
            "created_at": t.created_at,
            "latest_version": latest.version_number if latest else None,
            "latest_label": latest.label if latest else None,
        })
    return out


@router.post("/")
async def create_template(body: TemplateCreate, db: DbDep):
    t = PromptTemplateRow(
        id=str(uuid.uuid4())[:8],
        name=body.name,
        description=body.description,
        folder=body.folder,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@router.get("/{template_id}")
async def get_template(template_id: str, db: DbDep):
    result = await db.execute(select(PromptTemplateRow).where(PromptTemplateRow.id == template_id))
    t = result.scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Template not found")
    versions_result = await db.execute(
        select(PromptVersionRow)
        .where(PromptVersionRow.template_id == template_id)
        .order_by(PromptVersionRow.version_number)
    )
    versions = versions_result.scalars().all()
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "folder": t.folder,
        "created_at": t.created_at,
        "versions": [_version_to_dict(v) for v in versions],
    }


@router.put("/{template_id}")
async def update_template(template_id: str, body: TemplateUpdate, db: DbDep):
    result = await db.execute(select(PromptTemplateRow).where(PromptTemplateRow.id == template_id))
    t = result.scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Template not found")
    if body.name is not None:
        t.name = body.name
    if body.description is not None:
        t.description = body.description
    if body.folder is not None:
        t.folder = body.folder
    await db.commit()
    await db.refresh(t)
    return t


@router.delete("/{template_id}")
async def delete_template(template_id: str, db: DbDep):
    result = await db.execute(select(PromptTemplateRow).where(PromptTemplateRow.id == template_id))
    t = result.scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "Template not found")
    await db.delete(t)
    await db.commit()
    return {"deleted": template_id}


@router.post("/{template_id}/versions")
async def create_version(template_id: str, body: VersionCreate, db: DbDep):
    result = await db.execute(select(PromptTemplateRow).where(PromptTemplateRow.id == template_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Template not found")

    count_result = await db.execute(
        select(func.count()).where(PromptVersionRow.template_id == template_id)
    )
    count = count_result.scalar() or 0

    v = PromptVersionRow(
        id=str(uuid.uuid4()),
        template_id=template_id,
        version_number=count + 1,
        label=body.label,
        messages=body.messages,
        model=body.model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        commit_message=body.commit_message,
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return _version_to_dict(v)


@router.get("/{template_id}/versions/{version_id}")
async def get_version(template_id: str, version_id: str, db: DbDep):
    result = await db.execute(
        select(PromptVersionRow).where(
            PromptVersionRow.id == version_id,
            PromptVersionRow.template_id == template_id,
        )
    )
    v = result.scalar_one_or_none()
    if v is None:
        raise HTTPException(404, "Version not found")
    return _version_to_dict(v)


@router.put("/{template_id}/versions/{version_id}")
async def update_version_label(template_id: str, version_id: str, body: VersionLabelUpdate, db: DbDep):
    result = await db.execute(
        select(PromptVersionRow).where(
            PromptVersionRow.id == version_id,
            PromptVersionRow.template_id == template_id,
        )
    )
    v = result.scalar_one_or_none()
    if v is None:
        raise HTTPException(404, "Version not found")
    v.label = body.label
    await db.commit()
    await db.refresh(v)
    return _version_to_dict(v)


@router.delete("/{template_id}/versions/{version_id}")
async def delete_version(template_id: str, version_id: str, db: DbDep):
    result = await db.execute(
        select(PromptVersionRow).where(
            PromptVersionRow.id == version_id,
            PromptVersionRow.template_id == template_id,
        )
    )
    v = result.scalar_one_or_none()
    if v is None:
        raise HTTPException(404, "Version not found")
    await db.delete(v)
    await db.commit()
    return {"deleted": version_id}


@router.post("/{template_id}/versions/{version_id}/run")
async def run_version(template_id: str, version_id: str, body: RunRequest, db: DbDep):
    result = await db.execute(
        select(PromptVersionRow).where(
            PromptVersionRow.id == version_id,
            PromptVersionRow.template_id == template_id,
        )
    )
    v = result.scalar_one_or_none()
    if v is None:
        raise HTTPException(404, "Version not found")

    # Substitute variables in messages
    input_messages = []
    for msg in v.messages:
        new_msg = dict(msg)
        if isinstance(new_msg.get("content"), str):
            try:
                new_msg["content"] = new_msg["content"].format_map(body.variables)
            except KeyError:
                pass
        input_messages.append(new_msg)

    from vyuha.utils.llm_router import call as llm_call

    # Build prompt from messages
    system_msg = next((m["content"] for m in input_messages if m.get("role") == "system"), "")
    user_msgs = [m["content"] for m in input_messages if m.get("role") == "user"]
    prompt = "\n\n".join(user_msgs) if user_msgs else ""

    t0 = datetime.now(timezone.utc)
    resp = await llm_call(
        prompt=prompt,
        system=system_msg,
        max_tokens=v.max_tokens or 2048,
    )
    t1 = datetime.now(timezone.utc)
    latency_ms = (t1 - t0).total_seconds() * 1000

    return {
        "output": resp.text,
        "provider": resp.provider,
        "latency_ms": latency_ms,
        "input_messages": input_messages,
    }


@router.post("/{template_id}/compare")
async def compare_versions(template_id: str, body: CompareRequest, db: DbDep):
    from vyuha.utils.llm_router import call as llm_call

    results = []
    for vid in body.version_ids:
        result = await db.execute(
            select(PromptVersionRow).where(
                PromptVersionRow.id == vid,
                PromptVersionRow.template_id == template_id,
            )
        )
        v = result.scalar_one_or_none()
        if v is None:
            results.append({"version_id": vid, "error": "Version not found"})
            continue

        input_messages = []
        for msg in v.messages:
            new_msg = dict(msg)
            if isinstance(new_msg.get("content"), str):
                try:
                    new_msg["content"] = new_msg["content"].format_map(body.input_variables)
                except KeyError:
                    pass
            input_messages.append(new_msg)

        system_msg = next((m["content"] for m in input_messages if m.get("role") == "system"), "")
        user_msgs = [m["content"] for m in input_messages if m.get("role") == "user"]
        prompt = "\n\n".join(user_msgs) if user_msgs else ""

        t0 = datetime.now(timezone.utc)
        try:
            resp = await llm_call(prompt=prompt, system=system_msg, max_tokens=v.max_tokens or 2048)
            t1 = datetime.now(timezone.utc)
            latency_ms = (t1 - t0).total_seconds() * 1000
            results.append({
                "version_id": vid,
                "version_number": v.version_number,
                "label": v.label,
                "output": resp.text,
                "provider": resp.provider,
                "latency_ms": latency_ms,
            })
        except Exception as exc:
            results.append({"version_id": vid, "version_number": v.version_number, "label": v.label, "error": str(exc)})

    return {"versions": results}


def _version_to_dict(v: PromptVersionRow) -> dict:
    return {
        "id": v.id,
        "template_id": v.template_id,
        "version_number": v.version_number,
        "label": v.label,
        "messages": v.messages,
        "model": v.model,
        "temperature": v.temperature,
        "max_tokens": v.max_tokens,
        "commit_message": v.commit_message,
        "created_at": v.created_at,
    }
