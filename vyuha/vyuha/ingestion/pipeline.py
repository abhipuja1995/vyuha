"""
Production call ingestion pipeline.

Flow:
  FailedCallRecord → detect_failure_signals → extract_persona
    → generate_test_case → save → IngestionResult

A failed call is only converted if it has ≥1 failure signal.
The resulting TestCase is tagged with the source call ID and marked
linked_production_call so it can be traced back.
"""
from __future__ import annotations

import json
from typing import Any

import anthropic
import structlog

from vyuha.config import settings
from vyuha.ingestion.failure_detector import detect_failure_signals
from vyuha.ingestion.models import FailedCallRecord, IngestionResult
from vyuha.ingestion.persona_extractor import PersonaExtractor
from vyuha.models.test_case import (
    TestCase, TestCategory, PersonaConfig, Language, Emotion, NoiseProfile,
    ConversationGraph, ConversationNode, ConversationEdge, CodeSwitchConfig,
)

log = structlog.get_logger()

_GRAPH_GEN_PROMPT = """
A voice agent call failed. Convert it into a repeatable test case.

Failed call transcript:
{transcript}

Failure signals detected: {signals}

Generate a conversation graph that reproduces the failure condition:
- Nodes should represent caller utterances
- Edges should represent conditions (what the agent said/did to trigger the next user action)
- Include the exact user utterances that triggered the failure
- The last node should be terminal (is_terminal: true)

Return JSON:
{{
  "user_goal": "one sentence: what was the caller trying to achieve",
  "pass_criteria": "what the agent SHOULD have done to pass",
  "conversation_nodes": [
    {{"node_id": "n1", "utterance_template": "...", "is_terminal": false}}
  ],
  "conversation_edges": [
    {{"from_node": "n1", "to_node": "n2", "condition": "agent asked for..."}}
  ],
  "expected_tools": ["tool_name_1", "tool_name_2"],
  "ground_truth_end_state": {{"key": "expected_value"}},
  "tags": ["relevant", "tags"]
}}
"""


class IngestionPipeline:
    """
    Converts failed production calls into repeatable regression test cases.
    """

    def __init__(self) -> None:
        self._persona_extractor = PersonaExtractor()
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def ingest(self, record: FailedCallRecord) -> tuple[IngestionResult, TestCase] | None:
        """
        Returns None if the call does not have enough failure signals to warrant a test case.
        """
        signals = detect_failure_signals(record)
        if not signals:
            log.info("call_not_ingested_no_signals", call_id=record.call_id)
            return None

        log.info("ingesting_failed_call", call_id=record.call_id, signals=[s.value for s in signals])

        persona_data = await self._persona_extractor.extract(record)
        test_case = await self._generate_test_case(record, persona_data, signals)

        confidence = self._score_confidence(record, signals)
        log.info("call_ingested", call_id=record.call_id, test_id=test_case.test_id, confidence=confidence)

        return IngestionResult(
            call_id=record.call_id,
            failure_signals_detected=signals,
            extracted_persona=persona_data,
            generated_test_case_id=test_case.test_id,
            ingestion_confidence=confidence,
        ), test_case  # type: ignore[return-value]

    async def _generate_test_case(
        self,
        record: FailedCallRecord,
        persona_data,
        signals,
    ) -> TestCase:
        transcript_text = "\n".join(
            f"{t['role'].upper()}: {t['text']}" for t in record.transcript
        )
        prompt = _GRAPH_GEN_PROMPT.format(
            transcript=transcript_text[:4000],
            signals=[s.value for s in signals],
        )

        resp = await self._client.messages.create(
            model=settings.default_judge_model,
            max_tokens=2048,
            system="You are a QA expert. Respond with valid JSON only.",
            messages=[{"role": "user", "content": prompt}],
        )
        from vyuha.utils.llm import parse_llm_json
        data = parse_llm_json(resp.content[0].text)

        try:
            lang = Language(persona_data.language)
        except ValueError:
            lang = Language.ENGLISH_INDIAN

        try:
            emotion = Emotion(persona_data.emotion)
        except ValueError:
            emotion = Emotion.NEUTRAL

        try:
            noise = NoiseProfile(persona_data.noise_profile)
        except ValueError:
            noise = NoiseProfile.QUIET_INDOOR

        code_switch = None
        if persona_data.code_switch_detected and persona_data.secondary_language:
            try:
                secondary = Language(persona_data.secondary_language)
                code_switch = CodeSwitchConfig(primary_language=lang, secondary_language=secondary, switch_probability=0.4)
            except ValueError:
                pass

        persona = PersonaConfig(
            language=lang,
            accent_variant=persona_data.accent_variant,
            noise_profile=noise,
            emotion=emotion,
            speaking_rate=persona_data.speaking_rate,
            code_switch=code_switch,
            derived_from_call_id=record.call_id,
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
        from vyuha.models.test_case import ToolCallSpec
        tools = [ToolCallSpec(tool_name=t, mock_response={}) for t in data.get("expected_tools", [])]

        graph = ConversationGraph(
            start_node=nodes[0].node_id if nodes else "start",
            nodes=nodes,
            edges=edges,
        )

        tags = data.get("tags", []) + ["ingested", "regression", record.agent_id]
        tags += [s.value for s in signals]

        return TestCase(
            title=f"[INGESTED] {record.agent_id} — {', '.join(s.value for s in signals)}",
            category=TestCategory.REGRESSION,
            user_goal=data.get("user_goal", "Reproduce failure condition from production call"),
            persona_config=persona,
            conversation_graph=graph,
            tool_call_sequence=tools,
            ground_truth_end_state=data.get("ground_truth_end_state", {}),
            pass_criteria=data.get("pass_criteria", "Agent must complete the task without the failure that occurred in the source call"),
            created_by="INGESTION_PIPELINE",
            linked_production_call=record.call_id,
            tags=tags,
        )

    def _score_confidence(self, record: FailedCallRecord, signals) -> float:
        """
        Heuristic confidence that the ingested test case is useful.
        Higher with more signals, longer transcript, and known language.
        """
        score = 0.4
        score += min(len(signals) * 0.15, 0.3)
        score += min(len(record.transcript) / 20, 0.2)
        if record.language_detected != "en-IN":
            score += 0.1  # non-English failures are especially valuable
        return round(min(score, 1.0), 2)
