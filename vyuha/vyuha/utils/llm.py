"""Shared LLM output helpers used across generator, ingestion, and scoring."""
from __future__ import annotations

import json
from typing import Any


def strip_markdown_fences(raw: str) -> str:
    """Strip ```json ... ``` fences that LLMs add around JSON responses."""
    clean = raw.strip()
    if clean.startswith("```"):
        parts = clean.split("```")
        # parts[0] is empty, parts[1] is the fenced block
        inner = parts[1]
        if inner.startswith("json"):
            inner = inner[4:]
        clean = inner.strip()
    return clean


def parse_llm_json(raw: str) -> Any:
    """Parse JSON from an LLM response, handling markdown fences."""
    return json.loads(strip_markdown_fences(raw))
