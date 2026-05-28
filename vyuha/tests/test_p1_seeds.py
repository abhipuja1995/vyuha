"""Validate P1 language seed data integrity."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from seeds.p1_language_seeds import ALL_P1_SEEDS
from vyuha.models.test_case import Language, TestCategory, NoiseProfile


def test_p1_seed_count():
    assert len(ALL_P1_SEEDS) >= 8


def test_p1_languages_covered():
    langs = {tc.persona_config.language for tc in ALL_P1_SEEDS}
    required = {Language.KANNADA, Language.MALAYALAM, Language.MARATHI, Language.BENGALI}
    assert not (required - langs), f"Missing: {required - langs}"


def test_p1_critical_cases():
    criticals = [tc for tc in ALL_P1_SEEDS if tc.category == TestCategory.CRITICAL]
    assert len(criticals) >= 2, "Need at least 2 CRITICAL cases in P1"
    for tc in criticals:
        assert "FAIL" in tc.pass_criteria or "MUST" in tc.pass_criteria, \
            f"CRITICAL case {tc.test_id} pass_criteria too weak"


def test_p1_all_have_regression_tag():
    for tc in ALL_P1_SEEDS:
        assert "regression" in tc.tags, f"{tc.test_id} missing 'regression' tag"


def test_p1_graphs_valid():
    for tc in ALL_P1_SEEDS:
        graph = tc.conversation_graph
        node_ids = {n.node_id for n in graph.nodes}
        assert graph.start_node in node_ids, f"{tc.test_id}: start_node missing"
        terminals = [n for n in graph.nodes if n.is_terminal]
        assert terminals, f"{tc.test_id}: no terminal node"
        for edge in graph.edges:
            assert edge.from_node in node_ids
            assert edge.to_node in node_ids


def test_p1_has_interruption_case():
    tags_all = {tag for tc in ALL_P1_SEEDS for tag in tc.tags}
    assert "interruption" in tags_all, "P1 should include an interruption handling test"


def test_p1_has_compliance_case():
    tags_all = {tag for tc in ALL_P1_SEEDS for tag in tc.tags}
    assert any(t in tags_all for t in ["compliance", "regulatory", "disclosure"]), \
        "P1 should include a compliance/regulatory test"


def test_p1_otp_named_entity_case():
    otp_cases = [tc for tc in ALL_P1_SEEDS if "otp" in tc.tags]
    assert otp_cases, "Should have an OTP/named-entity accuracy test"
