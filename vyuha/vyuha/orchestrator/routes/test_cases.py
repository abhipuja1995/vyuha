from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.db import TestCaseRepo, get_db
from vyuha.models.test_case import TestCase, TestCategory, Language, PersonaConfig, ConversationGraph, ToolCallSpec

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]


class CreateTestCaseRequest(BaseModel):
    title: str
    category: TestCategory
    user_goal: str
    persona_config: dict[str, Any]
    conversation_graph: dict[str, Any]
    tool_call_sequence: list[dict[str, Any]] = []
    ground_truth_end_state: dict[str, Any] = {}
    pass_criteria: str
    tags: list[str] = []
    created_by: str = "analyst"


@router.post("/", response_model=TestCase)
async def create_test_case(req: CreateTestCaseRequest, db: DbDep) -> TestCase:
    tc = TestCase(
        title=req.title,
        category=req.category,
        user_goal=req.user_goal,
        persona_config=PersonaConfig(**req.persona_config),
        conversation_graph=ConversationGraph(**req.conversation_graph),
        tool_call_sequence=[ToolCallSpec(**t) for t in req.tool_call_sequence],
        ground_truth_end_state=req.ground_truth_end_state,
        pass_criteria=req.pass_criteria,
        tags=req.tags,
        created_by=req.created_by,
    )
    return await TestCaseRepo(db).save(tc)


@router.get("/", response_model=list[TestCase])
async def list_test_cases(
    db: DbDep,
    category: TestCategory | None = None,
    language: Language | None = None,
    tag: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[TestCase]:
    return await TestCaseRepo(db).list(category=category, language=language, tag=tag, limit=limit, offset=offset)


@router.get("/{test_id}", response_model=TestCase)
async def get_test_case(test_id: str, db: DbDep) -> TestCase:
    tc = await TestCaseRepo(db).get(test_id)
    if not tc:
        raise HTTPException(status_code=404, detail=f"Test case {test_id} not found")
    return tc


@router.delete("/{test_id}")
async def delete_test_case(test_id: str, db: DbDep) -> dict:
    deleted = await TestCaseRepo(db).delete(test_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Test case {test_id} not found")
    return {"deleted": test_id}
