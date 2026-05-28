"""Smoke tests for data models and scoring logic."""
from __future__ import annotations

import pytest

from vyuha.models.test_case import (
    TestCase, TestCategory, PersonaConfig, Language, Emotion, NoiseProfile,
    ConversationGraph, ConversationNode, ConversationEdge,
)
from vyuha.models.scoring import EvaAScore, EvaXScore, Verdict, RunResult, DiagnosticMetrics
from vyuha.models.rca import RCACode, RCATag
from vyuha.scoring.eva_a import EvaAScorer


def _make_test_case() -> TestCase:
    node_a = ConversationNode(node_id="start", utterance_template="I need to check my balance")
    node_b = ConversationNode(node_id="auth", utterance_template="My account number is 1234567")
    node_end = ConversationNode(node_id="done", utterance_template="Thank you", is_terminal=True)
    graph = ConversationGraph(
        start_node="start",
        nodes=[node_a, node_b, node_end],
        edges=[
            ConversationEdge(from_node="start", to_node="auth", condition="account number"),
            ConversationEdge(from_node="auth", to_node="done", condition="verified"),
        ],
    )
    return TestCase(
        title="Balance inquiry - Hindi caller",
        category=TestCategory.HAPPY_PATH,
        user_goal="Check account balance",
        persona_config=PersonaConfig(
            language=Language.HINDI,
            accent_variant="Bihari",
            noise_profile=NoiseProfile.MODERATE_INDOOR,
            emotion=Emotion.NEUTRAL,
        ),
        conversation_graph=graph,
        ground_truth_end_state={"balance_shown": True, "auth_completed": True},
        pass_criteria="Balance displayed correctly after authentication",
    )


def test_test_case_creation() -> None:
    tc = _make_test_case()
    assert tc.test_id.startswith("TC-")
    assert tc.category == TestCategory.HAPPY_PATH
    assert not tc.is_critical


def test_critical_test_case() -> None:
    tc = _make_test_case()
    tc.category = TestCategory.CRITICAL
    assert tc.is_critical


def test_eva_a_score_composite() -> None:
    score = EvaAScore(task_completion=1.0, faithfulness=0.9, speech_fidelity=0.8)
    # 1.0*0.5 + 0.9*0.3 + 0.8*0.2 = 0.5 + 0.27 + 0.16 = 0.93
    assert abs(score.composite - 0.93) < 0.001


def test_eva_a_score_pass_threshold() -> None:
    passing = EvaAScore(task_completion=1.0, faithfulness=0.9, speech_fidelity=0.9)
    failing = EvaAScore(task_completion=0.5, faithfulness=0.5, speech_fidelity=0.5)
    assert passing.passes
    assert not failing.passes


def test_eva_x_score_composite() -> None:
    score = EvaXScore(conciseness=0.8, conversation_progression=0.9, turn_taking=0.7)
    assert abs(score.composite - (0.8 + 0.9 + 0.7) / 3) < 0.001


def test_task_completion_scorer_exact_match() -> None:
    scorer = EvaAScorer()
    ground_truth = {"balance_shown": True, "auth_completed": True}
    actual = {"balance_shown": True, "auth_completed": True}
    assert scorer.score_task_completion(ground_truth, actual) == 1.0


def test_task_completion_scorer_partial() -> None:
    scorer = EvaAScorer()
    ground_truth = {"balance_shown": True, "auth_completed": True, "safety_flag": True}
    actual = {"balance_shown": True, "auth_completed": True, "safety_flag": False}
    assert abs(scorer.score_task_completion(ground_truth, actual) - 2 / 3) < 0.001


def test_rca_tag_from_code() -> None:
    tag = RCATag.from_code(RCACode.LLM_HALLUCINATION, turn_index=3, confidence=0.9)
    assert tag.code == RCACode.LLM_HALLUCINATION
    assert tag.turn_index == 3
    assert not tag.is_critical


def test_rca_safety_critical() -> None:
    tag = RCATag.from_code(RCACode.SAFETY_VIOLATION)
    assert tag.is_critical


def test_persona_config_defaults() -> None:
    persona = PersonaConfig(language=Language.TELUGU)
    assert persona.noise_profile == NoiseProfile.QUIET_INDOOR
    assert persona.emotion == Emotion.NEUTRAL
    assert persona.speaking_rate == 1.0
    assert persona.code_switch is None


def test_conversation_graph_navigation() -> None:
    tc = _make_test_case()
    graph = tc.conversation_graph
    start = graph.get_node("start")
    assert start is not None
    assert start.utterance_template == "I need to check my balance"
    assert graph.get_node("nonexistent") is None
