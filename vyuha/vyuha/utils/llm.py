"""Shared LLM output helpers used across generator, ingestion, and scoring."""
from __future__ import annotations

import json
from typing import Any


def strip_markdown_fences(raw: str) -> str:
    """
    Extract JSON from an LLM response that may contain leading prose,
    markdown code fences, or be a raw JSON object/array.

    Uses bracket-counting to find the complete JSON structure —
    avoids regex non-greedy issues with nested objects.
    """
    clean = raw.strip()

    # Find the first { or [ and extract the complete balanced structure
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        idx = clean.find(start_char)
        if idx == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(clean[idx:], idx):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    return clean[idx:i + 1]

    # Fallback: return as-is (will fail JSON parse with a clear error)
    return clean


def parse_llm_json(raw: str) -> Any:
    """Parse JSON from an LLM response, handling prose prefix and markdown fences."""
    return json.loads(strip_markdown_fences(raw))
