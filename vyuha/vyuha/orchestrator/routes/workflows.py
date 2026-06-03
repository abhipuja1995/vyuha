"""
/workflows — Import conversation workflows as test cases.

Supports three formats:
  1. Vyuha native JSON  — direct TestCase schema
  2. FutureAGI scenario graph — {type:"graph", nodes:[...], edges:[...]}
  3. Simple YAML/JSON  — compact human-authored format

  POST /workflows/import          upload a JSON/YAML workflow file
  POST /workflows/import/bulk     upload multiple workflows as a zip or JSON array
  GET  /workflows/schema          returns the Vyuha workflow JSON schema
  GET  /workflows/template        returns a starter template to download
"""
from __future__ import annotations

import json
import uuid
import yaml
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.db import TestCaseRepo, get_db
from vyuha.models.test_case import (
    TestCase, TestCategory, PersonaConfig, Language, Emotion, NoiseProfile,
    ConversationGraph, ConversationNode, ConversationEdge, ToolCallSpec,
    CodeSwitchConfig,
)

log = structlog.get_logger()
router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]

_ALLOWED_EXT = {".json", ".yaml", ".yml"}

# ── Parsers ───────────────────────────────────────────────────────────────────

def _load_text(content: bytes, filename: str) -> Any:
    ext = Path(filename).suffix.lower()
    text = content.decode("utf-8", errors="replace")
    if ext in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return json.loads(text)


def _parse_futureagi_graph(data: dict[str, Any], title_hint: str = "") -> TestCase:
    """
    Parse a FutureAGI ScenarioGraph format:
    {
      "type": "graph",
      "title": "...",
      "nodes": [{"id":"n1","type":"start|message|condition|end","content":"..."}],
      "edges": [{"from":"n1","to":"n2","condition":"..."}],
      "persona": {...},
      "pass_criteria": "...",
      "ground_truth": {...}
    }
    """
    raw_nodes = data.get("nodes", [])
    raw_edges = data.get("edges", [])
    start_node = next(
        (n["id"] for n in raw_nodes if n.get("type") == "start"), raw_nodes[0]["id"] if raw_nodes else "start"
    )
    nodes = [
        ConversationNode(
            node_id=n["id"],
            utterance_template=n.get("content") or n.get("utterance") or n.get("text", ""),
            is_terminal=n.get("type") == "end" or n.get("is_terminal", False),
        )
        for n in raw_nodes
    ]
    edges = [
        ConversationEdge(
            from_node=e.get("from") or e.get("from_node", ""),
            to_node=e.get("to") or e.get("to_node", ""),
            condition=e.get("condition", ""),
        )
        for e in raw_edges
    ]
    persona = _parse_persona(data.get("persona", {}))
    return TestCase(
        title=data.get("title") or title_hint or f"Imported workflow {uuid.uuid4().hex[:6].upper()}",
        category=_parse_category(data.get("category", "HAPPY_PATH")),
        user_goal=data.get("user_goal") or data.get("goal", ""),
        persona_config=persona,
        conversation_graph=ConversationGraph(start_node=start_node, nodes=nodes, edges=edges),
        tool_call_sequence=[ToolCallSpec(tool_name=t) for t in data.get("expected_tools", [])],
        ground_truth_end_state=data.get("ground_truth") or data.get("ground_truth_end_state", {}),
        pass_criteria=data.get("pass_criteria", ""),
        tags=data.get("tags", []) + ["imported", "workflow"],
        created_by="WORKFLOW_IMPORT",
    )


def _parse_vyuha_native(data: dict[str, Any]) -> TestCase:
    """Parse Vyuha's own TestCase JSON schema."""
    # Remove auto-generated fields so they get regenerated
    data.pop("test_id", None)
    data.pop("created_at", None)
    data.pop("created_by", None)

    persona_raw = data.get("persona_config", {})
    code_switch_raw = persona_raw.get("code_switch")
    code_switch = None
    if code_switch_raw:
        code_switch = CodeSwitchConfig(
            primary_language=Language(code_switch_raw["primary_language"]),
            secondary_language=Language(code_switch_raw["secondary_language"]),
            switch_probability=float(code_switch_raw.get("switch_probability", 0.3)),
        )

    persona = PersonaConfig(
        language=Language(persona_raw.get("language", "en-IN")),
        accent_variant=persona_raw.get("accent_variant", ""),
        noise_profile=NoiseProfile(persona_raw.get("noise_profile", "quiet_indoor")),
        emotion=Emotion(persona_raw.get("emotion", "neutral")),
        speaking_rate=float(persona_raw.get("speaking_rate", 1.0)),
        interruption_tendency=float(persona_raw.get("interruption_tendency", 0.1)),
        code_switch=code_switch,
        backstory=persona_raw.get("backstory", ""),
    )

    graph_raw = data.get("conversation_graph", {})
    nodes = [ConversationNode(**n) for n in graph_raw.get("nodes", [])]
    edges = [ConversationEdge(**e) for e in graph_raw.get("edges", [])]
    graph = ConversationGraph(
        start_node=graph_raw.get("start_node", nodes[0].node_id if nodes else "start"),
        nodes=nodes,
        edges=edges,
    )
    tools = [ToolCallSpec(**t) for t in data.get("tool_call_sequence", [])]
    return TestCase(
        title=data["title"],
        category=TestCategory(data.get("category", "HAPPY_PATH")),
        user_goal=data.get("user_goal", ""),
        persona_config=persona,
        conversation_graph=graph,
        tool_call_sequence=tools,
        ground_truth_end_state=data.get("ground_truth_end_state", {}),
        pass_criteria=data.get("pass_criteria", ""),
        tags=data.get("tags", []),
        created_by="WORKFLOW_IMPORT",
    )


def _parse_simple(data: dict[str, Any], title_hint: str = "") -> TestCase:
    """
    Parse a compact human-authored format:
    {
      "title": "...",
      "category": "CRITICAL",
      "persona": {"language":"hi","noise":"call_centre","emotion":"frustrated"},
      "turns": [
        {"role":"user","text":"Mujhe balance chahiye"},
        {"role":"agent_condition","text":"account number"}
      ],
      "pass_criteria": "...",
      "ground_truth": {"balance_shown": true}
    }
    """
    turns = data.get("turns", [])
    nodes: list[ConversationNode] = []
    edges: list[ConversationEdge] = []
    user_turns = [t for t in turns if t.get("role") == "user"]
    for i, turn in enumerate(user_turns):
        node_id = f"turn_{i}"
        is_last = i == len(user_turns) - 1
        nodes.append(ConversationNode(
            node_id=node_id,
            utterance_template=turn.get("text", ""),
            is_terminal=is_last,
        ))
        # edge condition = what agent says next (role=agent_condition)
        agent_conditions = [
            t for t in turns
            if t.get("role") == "agent_condition" and turns.index(t) > turns.index(turn)
        ]
        if not is_last and agent_conditions:
            edges.append(ConversationEdge(
                from_node=node_id,
                to_node=f"turn_{i+1}",
                condition=agent_conditions[0].get("text", ""),
            ))
        elif not is_last:
            edges.append(ConversationEdge(
                from_node=node_id, to_node=f"turn_{i+1}", condition=""
            ))

    persona_raw = data.get("persona", {})
    persona = _parse_persona(persona_raw)
    return TestCase(
        title=data.get("title") or title_hint or "Imported workflow",
        category=_parse_category(data.get("category", "HAPPY_PATH")),
        user_goal=data.get("user_goal") or data.get("goal", ""),
        persona_config=persona,
        conversation_graph=ConversationGraph(
            start_node=nodes[0].node_id if nodes else "start",
            nodes=nodes,
            edges=edges,
        ),
        tool_call_sequence=[ToolCallSpec(tool_name=t) for t in data.get("expected_tools", [])],
        ground_truth_end_state=data.get("ground_truth") or data.get("ground_truth_end_state", {}),
        pass_criteria=data.get("pass_criteria", ""),
        tags=data.get("tags", []) + ["imported"],
        created_by="WORKFLOW_IMPORT",
    )


def _parse_persona(raw: dict[str, Any]) -> PersonaConfig:
    def _lang(v: str) -> Language:
        try: return Language(v)
        except ValueError: return Language.ENGLISH_INDIAN

    def _noise(v: str) -> NoiseProfile:
        v_map = {"quiet": "quiet_indoor", "moderate": "moderate_indoor",
                 "outdoor": "busy_outdoor", "call_center": "call_centre", "mobile": "mobile_degraded"}
        try: return NoiseProfile(v_map.get(v, v))
        except ValueError: return NoiseProfile.QUIET_INDOOR

    def _emotion(v: str) -> Emotion:
        try: return Emotion(v)
        except ValueError: return Emotion.NEUTRAL

    code_switch = None
    cs_raw = raw.get("code_switch") or raw.get("code_switching")
    if cs_raw:
        try:
            code_switch = CodeSwitchConfig(
                primary_language=_lang(cs_raw.get("primary", "en-IN")),
                secondary_language=_lang(cs_raw.get("secondary", "hi")),
                switch_probability=float(cs_raw.get("probability", 0.3)),
            )
        except Exception:
            pass

    return PersonaConfig(
        language=_lang(raw.get("language", raw.get("lang", "en-IN"))),
        accent_variant=raw.get("accent", raw.get("accent_variant", "")),
        noise_profile=_noise(raw.get("noise", raw.get("noise_profile", "quiet_indoor"))),
        emotion=_emotion(raw.get("emotion", "neutral")),
        speaking_rate=float(raw.get("speaking_rate", raw.get("rate", 1.0))),
        backstory=raw.get("backstory", ""),
        code_switch=code_switch,
    )


def _parse_category(v: str) -> TestCategory:
    try: return TestCategory(v.upper())
    except ValueError: return TestCategory.HAPPY_PATH


def _detect_and_parse(data: Any, filename: str = "") -> TestCase:
    """Auto-detect format and parse."""
    if isinstance(data, list):
        raise ValueError("For bulk import use /workflows/import/bulk")

    fmt = data.get("format", "")
    # FutureAGI scenario graph
    if data.get("type") in ("graph", "scenario_graph") or fmt == "futureagi":
        return _parse_futureagi_graph(data, Path(filename).stem)
    # Vyuha native (has conversation_graph + persona_config keys)
    if "conversation_graph" in data and "persona_config" in data:
        return _parse_vyuha_native(data)
    # Compact/simple format (has "turns" key or just nodes+edges with different naming)
    if "turns" in data or ("nodes" not in data and "title" in data):
        return _parse_simple(data, Path(filename).stem)
    # Default: try FutureAGI graph (has nodes/edges)
    return _parse_futureagi_graph(data, Path(filename).stem)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/import")
async def import_workflow(
    db: DbDep,
    file: UploadFile = File(..., description="JSON or YAML workflow file"),
    save: bool = Form(default=True, description="Save to DB immediately, or return preview only"),
    tags: str = Form(default="", description="Comma-separated extra tags to apply"),
) -> dict[str, Any]:
    """
    Upload a workflow file (JSON/YAML) and convert it to a TestCase.
    Supports Vyuha native, FutureAGI scenario graph, and compact formats.
    Set save=false to preview without persisting.
    """
    ext = Path(file.filename or "workflow.json").suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported format '{ext}'. Use .json, .yaml, or .yml")

    content = await file.read()
    try:
        data = _load_text(content, file.filename or "workflow.json")
    except Exception as exc:
        raise HTTPException(400, f"Parse error: {exc}")

    try:
        tc = _detect_and_parse(data, file.filename or "")
    except Exception as exc:
        raise HTTPException(422, f"Workflow conversion failed: {exc}")

    # Apply extra tags
    if tags:
        extra = [t.strip() for t in tags.split(",") if t.strip()]
        tc.tags = list(set(tc.tags + extra))

    if save:
        await TestCaseRepo(db).save(tc)
        log.info("workflow_imported", test_id=tc.test_id, title=tc.title)

    return {
        "imported": save,
        "test_case": tc.model_dump(mode="json"),
        "test_case_id": tc.test_id,
        "format_detected": (
            "futureagi_graph" if data.get("type") in ("graph", "scenario_graph")
            else "vyuha_native" if "conversation_graph" in data
            else "compact"
        ),
    }


@router.post("/import/bulk")
async def import_bulk_workflows(
    db: DbDep,
    file: UploadFile = File(..., description="JSON array of workflows, or ZIP of JSON/YAML files"),
    save: bool = Form(default=True),
) -> dict[str, Any]:
    """
    Bulk import multiple workflows from a JSON array or ZIP archive.
    """
    filename = file.filename or "workflows.json"
    content = await file.read()

    workflows: list[Any] = []

    if filename.endswith(".zip"):
        import zipfile
        try:
            with zipfile.ZipFile(BytesIO(content)) as zf:
                for name in zf.namelist():
                    ext = Path(name).suffix.lower()
                    if ext in _ALLOWED_EXT:
                        workflows.append((_load_text(zf.read(name), name), name))
        except Exception as exc:
            raise HTTPException(400, f"ZIP error: {exc}")
    else:
        try:
            data = _load_text(content, filename)
        except Exception as exc:
            raise HTTPException(400, f"Parse error: {exc}")
        if not isinstance(data, list):
            data = [data]
        workflows = [(item, filename) for item in data]

    results = []
    for raw, fname in workflows:
        try:
            tc = _detect_and_parse(raw, fname)
            if save:
                await TestCaseRepo(db).save(tc)
            results.append({"status": "ok", "test_case_id": tc.test_id, "title": tc.title})
        except Exception as exc:
            results.append({"status": "error", "file": fname, "error": str(exc)})

    ok = [r for r in results if r["status"] == "ok"]
    log.info("bulk_import_done", total=len(results), ok=len(ok))
    return {"total": len(results), "imported": len(ok), "errors": len(results) - len(ok), "results": results}


@router.get("/schema")
async def get_workflow_schema() -> dict[str, Any]:
    """Return the JSON schema for Vyuha's workflow format."""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Vyuha Workflow",
        "description": "Compact workflow definition that converts to a Vyuha TestCase",
        "type": "object",
        "required": ["title", "persona", "turns", "pass_criteria"],
        "properties": {
            "title": {"type": "string"},
            "category": {"type": "string", "enum": ["HAPPY_PATH","EDGE_CASE","FAILURE_MODE","CRITICAL","REGRESSION"]},
            "user_goal": {"type": "string"},
            "persona": {
                "type": "object",
                "properties": {
                    "language": {"type": "string", "description": "BCP-47 code: hi, te, ta, or, kn, ml, mr, bn, en-IN"},
                    "accent": {"type": "string"},
                    "noise": {"type": "string", "enum": ["quiet_indoor","moderate_indoor","busy_outdoor","call_centre","mobile_degraded","speakerphone"]},
                    "emotion": {"type": "string", "enum": ["neutral","frustrated","anxious","urgent","calm","distressed"]},
                    "speaking_rate": {"type": "number", "minimum": 0.5, "maximum": 2.0},
                    "backstory": {"type": "string"},
                    "code_switch": {
                        "type": "object",
                        "properties": {
                            "primary": {"type": "string"},
                            "secondary": {"type": "string"},
                            "probability": {"type": "number", "minimum": 0, "maximum": 1},
                        }
                    }
                }
            },
            "turns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "enum": ["user","agent_condition"]},
                        "text": {"type": "string"}
                    }
                }
            },
            "expected_tools": {"type": "array", "items": {"type": "string"}},
            "ground_truth": {"type": "object"},
            "pass_criteria": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        }
    }


@router.get("/template")
async def get_workflow_template() -> dict[str, Any]:
    """Return a starter workflow template."""
    return {
        "title": "Hindi caller — balance inquiry with code-switching",
        "category": "HAPPY_PATH",
        "user_goal": "Check account balance",
        "persona": {
            "language": "hi",
            "accent": "Delhi",
            "noise": "moderate_indoor",
            "emotion": "neutral",
            "speaking_rate": 1.0,
            "backstory": "Customer calling bank IVR",
            "code_switch": {
                "primary": "hi",
                "secondary": "en-IN",
                "probability": 0.4
            }
        },
        "turns": [
            {"role": "user", "text": "Mujhe apna account balance check karna hai"},
            {"role": "agent_condition", "text": "account number"},
            {"role": "user", "text": "Mera account number hai 9876543210"},
            {"role": "agent_condition", "text": "balance"},
            {"role": "user", "text": "Okay, thank you"}
        ],
        "expected_tools": ["authenticate_user", "get_account_balance"],
        "ground_truth": {"balance_shown": True, "auth_completed": True},
        "pass_criteria": "Agent correctly identifies Hindi intent, authenticates, and reads balance. No language mismatch.",
        "tags": ["hindi", "banking", "balance", "code-switching"]
    }
