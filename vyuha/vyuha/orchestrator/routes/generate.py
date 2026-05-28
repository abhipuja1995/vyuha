from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.db import TestCaseRepo, get_db
from vyuha.generator.test_generator import TestCaseGenerator
from vyuha.models.test_case import Language, TestCase

router = APIRouter()
generator = TestCaseGenerator()

DbDep = Annotated[AsyncSession, Depends(get_db)]


class GenerateRequest(BaseModel):
    system_prompt: str
    knowledge_base: str = ""
    tools: list[dict[str, Any]] = []
    flow_description: str = ""
    language: Language = Language.ENGLISH_INDIAN
    use_cases: str = ""
    count: int = 50


@router.post("/from-prompt", response_model=list[TestCase])
async def generate_from_prompt(req: GenerateRequest, db: DbDep) -> list[TestCase]:
    if len(req.system_prompt) < 100:
        raise HTTPException(
            status_code=400,
            detail="System prompt too short (minimum 100 characters)",
        )

    test_cases = await generator.generate(
        system_prompt=req.system_prompt,
        knowledge_base=req.knowledge_base,
        tools=req.tools,
        flow_description=req.flow_description,
        language=req.language,
        use_cases=req.use_cases,
        count=req.count,
    )

    repo = TestCaseRepo(db)
    for tc in test_cases:
        await repo.save(tc)

    return test_cases
