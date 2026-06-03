from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

from vyuha.config import settings
from vyuha.utils import llm_router
from vyuha.models.test_case import (
    TestCase, TestCategory, PersonaConfig, Language, Emotion, NoiseProfile,
    ConversationGraph, ConversationNode, ConversationEdge, ToolCallSpec,
)

log = structlog.get_logger()

_GENERATION_SYSTEM = """You are a QA expert generating comprehensive test cases for a voice AI agent.
Always respond with valid JSON conforming to the requested schema. Be specific and realistic."""

_GENERATION_PROMPT = """
Analyze this voice agent configuration and generate {count} test cases.

Distribution required:
- Happy Path: 30% ({happy} cases) — caller achieves goal smoothly
- Edge Case: 40% ({edge} cases) — unusual but valid caller behaviour
- Failure Mode: 30% ({failure} cases) — agent must handle errors, impossible requests, out-of-scope

Agent configuration:
---
System Prompt: {system_prompt}

Knowledge Base excerpt: {knowledge_base}

Available Tools: {tools}

Conversation Flow: {flow_description}
---

Target user profile:
- Primary language: {language}
- Use cases: {use_cases}

For each test case, generate:
{{
  "title": string,
  "category": "HAPPY_PATH" | "EDGE_CASE" | "FAILURE_MODE",
  "user_goal": string (what the caller is trying to achieve),
  "persona": {{
    "language": string (BCP-47 code),
    "emotion": "neutral" | "frustrated" | "anxious" | "urgent",
    "accent_variant": string,
    "noise_profile": "quiet_indoor" | "moderate_indoor" | "busy_outdoor" | "call_centre" | "mobile_degraded" | "speakerphone"
  }},
  "conversation_nodes": [
    {{"node_id": string, "utterance_template": string, "is_terminal": bool}}
  ],
  "conversation_edges": [
    {{"from_node": string, "to_node": string, "condition": string}}
  ],
  "expected_tools": [string],
  "ground_truth_end_state": {{field: value}},
  "pass_criteria": string,
  "tags": [string]
}}

Return JSON: {{"test_cases": [<array of test cases>]}}
"""


class TestCaseGenerator:
    """
    Generates test cases from agent configuration artefacts.
    Uses the best available LLM (auto-routed: Claude → GPT-4o → Ollama).
    Distribution: 30% Happy Path, 40% Edge Case, 30% Failure Mode.
    """

    async def generate(
        self,
        system_prompt: str,
        knowledge_base: str = "",
        tools: list[dict[str, Any]] | None = None,
        flow_description: str = "",
        language: Language = Language.ENGLISH_INDIAN,
        use_cases: str = "",
        count: int = 50,
    ) -> list[TestCase]:
        if len(system_prompt) < 100:
            raise ValueError("System prompt too short to generate meaningful test cases")

        happy = int(count * 0.30)
        edge = int(count * 0.40)
        failure = count - happy - edge

        prompt = _GENERATION_PROMPT.format(
            count=count,
            happy=happy,
            edge=edge,
            failure=failure,
            system_prompt=system_prompt[:3000],
            knowledge_base=knowledge_base[:2000] if knowledge_base else "Not provided",
            tools=json.dumps(tools or [], indent=2)[:1000],
            flow_description=flow_description[:1000] if flow_description else "Not provided",
            language=language.value,
            use_cases=use_cases or "General customer support",
        )

        provider = llm_router.active_provider()
        log.info("generating_test_cases", count=count, language=language, provider=provider)

        try:
            llm_resp = await llm_router.call(prompt, system=_GENERATION_SYSTEM, max_tokens=8192)
        except RuntimeError as exc:
            log.error("test_generator_no_llm", error=str(exc))
            raise

        from vyuha.utils.llm import parse_llm_json
        try:
            data = parse_llm_json(llm_resp.text)
        except json.JSONDecodeError:
            log.error("test_generator_json_parse_failed", raw=llm_resp.text[:300])
            return []

        test_cases = []
        for tc_data in data.get("test_cases", []):
            try:
                test_cases.append(self._parse_test_case(tc_data, language))
            except Exception as exc:
                log.warning("test_case_parse_failed", error=str(exc), title=tc_data.get("title"))

        log.info("test_cases_generated", count=len(test_cases))
        return test_cases

    def _parse_test_case(self, data: dict[str, Any], default_language: Language) -> TestCase:
        persona_data = data.get("persona", {})
        try:
            lang = Language(persona_data.get("language", default_language.value))
        except ValueError:
            lang = default_language

        persona = PersonaConfig(
            language=lang,
            emotion=Emotion(persona_data.get("emotion", "neutral")),
            accent_variant=persona_data.get("accent_variant", ""),
            noise_profile=NoiseProfile(persona_data.get("noise_profile", "quiet_indoor")),
        )

        nodes = [
            ConversationNode(
                node_id=n["node_id"],
                utterance_template=n["utterance_template"],
                is_terminal=n.get("is_terminal", False),
            )
            for n in data.get("conversation_nodes", [])
        ]
        edges = [
            ConversationEdge(
                from_node=e["from_node"],
                to_node=e["to_node"],
                condition=e["condition"],
            )
            for e in data.get("conversation_edges", [])
        ]

        graph = ConversationGraph(
            start_node=nodes[0].node_id if nodes else "start",
            nodes=nodes,
            edges=edges,
        )

        tool_specs = [
            ToolCallSpec(tool_name=t, mock_response={})
            for t in data.get("expected_tools", [])
        ]

        return TestCase(
            title=data["title"],
            category=TestCategory(data["category"]),
            user_goal=data["user_goal"],
            persona_config=persona,
            conversation_graph=graph,
            tool_call_sequence=tool_specs,
            ground_truth_end_state=data.get("ground_truth_end_state", {}),
            pass_criteria=data.get("pass_criteria", ""),
            tags=data.get("tags", []),
            created_by="AUTO_GENERATED",
        )
