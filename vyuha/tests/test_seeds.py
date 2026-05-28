"""Validate seed data integrity — no DB required."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from seeds.p0_language_seeds import ALL_P0_SEEDS
from vyuha.models.test_case import TestCategory, Language, NoiseProfile


def test_seed_count() -> None:
    assert len(ALL_P0_SEEDS) >= 11


def test_critical_seeds_have_safety_pass_criteria() -> None:
    critical = [tc for tc in ALL_P0_SEEDS if tc.category == TestCategory.CRITICAL]
    assert len(critical) >= 2
    for tc in critical:
        assert tc.pass_criteria, f"CRITICAL case {tc.test_id} must have pass_criteria"


def test_all_seeds_have_ground_truth() -> None:
    for tc in ALL_P0_SEEDS:
        assert tc.ground_truth_end_state, f"{tc.test_id} missing ground_truth_end_state"


def test_p0_languages_covered() -> None:
    languages_present = {tc.persona_config.language for tc in ALL_P0_SEEDS}
    p0_required = {Language.TELUGU, Language.TAMIL, Language.HINDI, Language.ODIA, Language.ENGLISH_INDIAN}
    missing = p0_required - languages_present
    assert not missing, f"Missing P0 languages: {missing}"


def test_code_switching_seeds_exist() -> None:
    cs_seeds = [tc for tc in ALL_P0_SEEDS if tc.persona_config.code_switch is not None]
    assert len(cs_seeds) >= 4, "Need at least 4 code-switching test cases"


def test_noise_profiles_covered() -> None:
    profiles_present = {tc.persona_config.noise_profile for tc in ALL_P0_SEEDS}
    # At minimum: quiet, moderate, busy outdoor, call centre, mobile
    required = {
        NoiseProfile.QUIET_INDOOR,
        NoiseProfile.MODERATE_INDOOR,
        NoiseProfile.BUSY_OUTDOOR,
        NoiseProfile.MOBILE_DEGRADED,
        NoiseProfile.CALL_CENTRE,
    }
    missing = required - profiles_present
    assert not missing, f"Missing noise profiles: {missing}"


def test_each_seed_has_regression_tag() -> None:
    for tc in ALL_P0_SEEDS:
        assert "regression" in tc.tags, f"{tc.test_id} missing 'regression' tag for CI suite"


def test_critical_seeds_have_tool_call_sequence() -> None:
    critical = [tc for tc in ALL_P0_SEEDS if tc.category == TestCategory.CRITICAL]
    for tc in critical:
        assert tc.tool_call_sequence, f"CRITICAL case {tc.test_id} must have expected tool calls"


def test_conversation_graphs_valid() -> None:
    for tc in ALL_P0_SEEDS:
        graph = tc.conversation_graph
        # start_node must exist
        start = graph.get_node(graph.start_node)
        assert start is not None, f"{tc.test_id}: start_node '{graph.start_node}' not in nodes"
        # all edge nodes must exist
        node_ids = {n.node_id for n in graph.nodes}
        for edge in graph.edges:
            assert edge.from_node in node_ids, f"{tc.test_id}: edge from_node '{edge.from_node}' missing"
            assert edge.to_node in node_ids, f"{tc.test_id}: edge to_node '{edge.to_node}' missing"
        # must have at least one terminal node
        terminals = [n for n in graph.nodes if n.is_terminal]
        assert terminals, f"{tc.test_id}: no terminal node in conversation graph"
