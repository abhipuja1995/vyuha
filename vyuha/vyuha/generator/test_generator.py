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
        is_local = provider.startswith("ollama")
        log.info("generating_test_cases", count=count, language=language, provider=provider)

        from vyuha.utils.llm import parse_llm_json

        if is_local:
            # Local small models can reliably produce one test case at a time.
            # Generate individually and collect results.
            return await self._generate_one_by_one(
                count=count,
                system_prompt=system_prompt,
                knowledge_base=knowledge_base,
                tools=tools or [],
                flow_description=flow_description,
                language=language,
                use_cases=use_cases,
            )

        # Cloud LLMs: generate all in one request
        try:
            llm_resp = await llm_router.call(prompt, system=_GENERATION_SYSTEM, max_tokens=8192)
        except RuntimeError as exc:
            log.error("test_generator_no_llm", error=str(exc))
            raise

        try:
            data = parse_llm_json(llm_resp.text)
        except (json.JSONDecodeError, ValueError) as exc:
            log.error("test_generator_json_parse_failed", error=str(exc), raw=llm_resp.text[:400])
            raise ValueError(
                f"LLM returned unparseable output. Raw: {llm_resp.text[:200]}"
            ) from exc

        test_cases = []
        for tc_data in data.get("test_cases", []):
            try:
                test_cases.append(self._parse_test_case(tc_data, language))
            except Exception as exc:
                log.warning("test_case_parse_failed", error=str(exc), title=tc_data.get("title"))

        log.info("test_cases_generated", count=len(test_cases))
        return test_cases

    async def _generate_one_by_one(
        self,
        count: int,
        system_prompt: str,
        knowledge_base: str,
        tools: list,
        flow_description: str,
        language: Language,
        use_cases: str,
    ) -> list[TestCase]:
        """
        For local Ollama models: generate one test case per request.
        Ensures complete JSON output within token limits.
        """
        import asyncio
        from vyuha.utils.llm import parse_llm_json

        categories = (
            ["HAPPY_PATH"] * max(1, int(count * 0.30)) +
            ["EDGE_CASE"] * max(1, int(count * 0.40)) +
            ["FAILURE_MODE"] * max(1, count - int(count * 0.30) - int(count * 0.40))
        )[:count]

        _SINGLE_PROMPT = """Generate exactly ONE test case for this voice AI agent.

Agent configuration:
System Prompt: {system_prompt}
Use cases: {use_cases}
Language: {language}

Category: {category}

Return ONLY a JSON object (no explanation, no prose):
{{
  "title": "...",
  "category": "{category}",
  "user_goal": "...",
  "persona": {{
    "language": "{language_code}",
    "emotion": "neutral|frustrated|anxious|urgent",
    "accent_variant": "",
    "noise_profile": "quiet_indoor|moderate_indoor|busy_outdoor|call_centre|mobile_degraded"
  }},
  "conversation_nodes": [
    {{"node_id": "start", "utterance_template": "...", "is_terminal": false}},
    {{"node_id": "end", "utterance_template": "...", "is_terminal": true}}
  ],
  "conversation_edges": [
    {{"from_node": "start", "to_node": "end", "condition": "..."}}
  ],
  "expected_tools": [],
  "ground_truth_end_state": {{}},
  "pass_criteria": "...",
  "tags": ["{tag}"]
}}"""

        test_cases: list = []
        for i, category in enumerate(categories):
            tag = category.lower().replace("_", "-")
            single_prompt = _SINGLE_PROMPT.format(
                system_prompt=system_prompt[:1500],
                use_cases=use_cases or "General customer support",
                language=language.value,
                language_code=language.value,
                category=category,
                tag=tag,
            )
            try:
                llm_resp = await llm_router.call(
                    single_prompt,
                    system="You are a QA expert. Respond with a single valid JSON object only. No explanation.",
                    max_tokens=1200,
                )
                try:
                    from vyuha.utils.llm import parse_llm_json
                    data = parse_llm_json(llm_resp.text)
                    tc = self._parse_test_case(data, language)
                    test_cases.append(tc)
                    log.debug("single_test_case_generated", index=i + 1, total=count, title=tc.title)
                except Exception as exc:
                    log.warning("single_test_case_parse_failed", index=i + 1, error=str(exc))
            except Exception as exc:
                log.warning("single_test_case_llm_failed", index=i + 1, error=str(exc))

        log.info("test_cases_generated", count=len(test_cases), mode="one_by_one")
        return test_cases

    def _parse_test_case(self, data: dict[str, Any], default_language: Language) -> TestCase:
        persona_data = data.get("persona", {})
        try:
            lang = Language(persona_data.get("language", default_language.value))
        except ValueError:
            lang = default_language

        def _safe_emotion(v) -> Emotion:
            try: return Emotion(v or "neutral")
            except ValueError: return Emotion.NEUTRAL

        def _safe_noise(v) -> NoiseProfile:
            try: return NoiseProfile(v or "quiet_indoor")
            except ValueError: return NoiseProfile.QUIET_INDOOR

        persona = PersonaConfig(
            language=lang,
            emotion=_safe_emotion(persona_data.get("emotion")),
            accent_variant=persona_data.get("accent_variant") or "",
            noise_profile=_safe_noise(persona_data.get("noise_profile")),
            backstory=persona_data.get("backstory") or "",
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
