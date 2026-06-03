from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.db import TestCaseRepo, get_db
from vyuha.generator.test_generator import TestCaseGenerator
from vyuha.models.test_case import Language, TestCase

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _get_generator() -> TestCaseGenerator:
    """Lazy singleton — avoids creating the Anthropic client at import time."""
    import functools
    if not hasattr(_get_generator, "_instance"):
        _get_generator._instance = TestCaseGenerator()  # type: ignore[attr-defined]
    return _get_generator._instance  # type: ignore[attr-defined]


class GenerateRequest(BaseModel):
    system_prompt: str
    knowledge_base: str = ""
    tools: list[dict[str, Any]] = []
    flow_description: str = ""
    language: Language = Language.ENGLISH_INDIAN
    use_cases: str = ""
    count: int = 50


@router.post("/from-prompt")
async def generate_from_prompt(req: GenerateRequest, db: DbDep) -> dict:
    if len(req.system_prompt) < 100:
        raise HTTPException(
            status_code=400,
            detail="System prompt too short (minimum 100 characters)",
        )

    try:
        test_cases = await _get_generator().generate(
            system_prompt=req.system_prompt,
            knowledge_base=req.knowledge_base,
            tools=req.tools,
            flow_description=req.flow_description,
            language=req.language,
            use_cases=req.use_cases,
            count=req.count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if not test_cases:
        raise HTTPException(
            status_code=422,
            detail="LLM returned no parseable test cases. Try a more detailed prompt or reduce the count.",
        )

    repo = TestCaseRepo(db)
    for tc in test_cases:
        await repo.save(tc)

    return {"count": len(test_cases), "test_cases": [tc.model_dump(mode="json") for tc in test_cases]}
