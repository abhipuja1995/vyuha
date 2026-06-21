"""
/agents — Agent definitions (VAPI/Retell/LiveKit) for voice platform integration (FutureAGI-parity).
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.db import get_db
from vyuha.db.tables import AgentDefinitionRow

log = structlog.get_logger()
router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    agent_type: str = "text"
    voice_provider: str | None = None
    config: dict[str, Any] = {}
    system_prompt: str = ""


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    agent_type: str | None = None
    voice_provider: str | None = None
    config: dict[str, Any] | None = None
    system_prompt: str | None = None
    is_active: bool | None = None


class ImportCallRequest(BaseModel):
    call_id: str


def _mask_config(config: dict) -> dict:
    masked = copy.deepcopy(config)
    if "api_key" in masked:
        masked["api_key"] = "***"
    return masked


def _agent_to_dict(a: AgentDefinitionRow, mask: bool = False) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "description": a.description,
        "agent_type": a.agent_type,
        "voice_provider": a.voice_provider,
        "config": _mask_config(a.config) if mask else a.config,
        "system_prompt": a.system_prompt,
        "is_active": a.is_active,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


@router.get("/")
async def list_agents(db: DbDep):
    result = await db.execute(select(AgentDefinitionRow).order_by(AgentDefinitionRow.created_at.desc()))
    return [_agent_to_dict(a) for a in result.scalars().all()]


@router.post("/")
async def create_agent(body: AgentCreate, db: DbDep):
    a = AgentDefinitionRow(
        id=str(uuid.uuid4())[:8],
        name=body.name,
        description=body.description,
        agent_type=body.agent_type,
        voice_provider=body.voice_provider,
        config=body.config,
        system_prompt=body.system_prompt,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return _agent_to_dict(a, mask=True)


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: DbDep):
    result = await db.execute(select(AgentDefinitionRow).where(AgentDefinitionRow.id == agent_id))
    a = result.scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Agent not found")
    return _agent_to_dict(a, mask=True)


@router.put("/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdate, db: DbDep):
    result = await db.execute(select(AgentDefinitionRow).where(AgentDefinitionRow.id == agent_id))
    a = result.scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Agent not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(a, field, val)
    await db.commit()
    await db.refresh(a)
    return _agent_to_dict(a, mask=True)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: DbDep):
    result = await db.execute(select(AgentDefinitionRow).where(AgentDefinitionRow.id == agent_id))
    a = result.scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Agent not found")
    await db.delete(a)
    await db.commit()
    return {"deleted": agent_id}


@router.post("/{agent_id}/test")
async def test_agent_connection(agent_id: str, db: DbDep):
    result = await db.execute(select(AgentDefinitionRow).where(AgentDefinitionRow.id == agent_id))
    a = result.scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Agent not found")

    provider = (a.voice_provider or "").lower()
    api_key = a.config.get("api_key", "")

    if provider == "vapi":
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.vapi.ai/assistant",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                return {"connected": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as exc:
            return {"connected": False, "error": str(exc)}

    elif provider == "retell":
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.retellai.com/list-agents",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                return {"connected": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as exc:
            return {"connected": False, "error": str(exc)}

    elif provider == "livekit":
        return {"connected": True, "note": "LiveKit connection validated via webhook"}

    else:
        return {"connected": True, "note": "Manual agent, no connection test available"}


@router.post("/{agent_id}/import-call")
async def import_call(agent_id: str, body: ImportCallRequest, db: DbDep):
    result = await db.execute(select(AgentDefinitionRow).where(AgentDefinitionRow.id == agent_id))
    a = result.scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Agent not found")

    provider = (a.voice_provider or "").lower()
    api_key = a.config.get("api_key", "")

    if provider == "vapi":
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.vapi.ai/call/{body.call_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                if resp.status_code != 200:
                    raise HTTPException(resp.status_code, f"VAPI error: {resp.text}")
                data = resp.json()
                return {
                    "call_id": body.call_id,
                    "transcript": data.get("transcript", ""),
                    "artifact": data.get("artifact"),
                }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"Failed to fetch call: {exc}")

    return {
        "call_id": body.call_id,
        "transcript": None,
        "note": f"Call import not supported for provider: {provider or 'text'}",
    }
