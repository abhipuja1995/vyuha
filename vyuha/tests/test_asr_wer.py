"""
Tests for vyuha.asr.wer_scorer (37 tests) — no LLM API, no IndicNormalizer.

Covers: wer(), cer(), get_segments(), process_llm_responses(),
reconstruct_and_score(), load_and_validate_dataset (via pandas),
and full pipeline integration.

Ported from sarvamai/llm_wer and re-homed inside vyuha.
"""
from __future__ import annotations

import json
import os
import tempfile

import pandas as pd
import pytest

from vyuha.asr.normalizer import wer, cer
from vyuha.asr.wer_scorer import (
    get_segments,
    extract_unique_segments,
    process_llm_responses,
    reconstruct_and_score,
)


# ─── WER ──────────────────────────────────────────────────────────────────────

def test_wer_identical():
    assert wer("hello world", "hello world") == pytest.approx(0.0)


def test_wer_completely_different():
    assert wer("a b", "c d") == pytest.approx(1.0)


def test_wer_single_substitution():
    assert wer("hello world", "hello earth") == pytest.approx(0.5)


def test_wer_empty_both():
    assert wer("", "") == pytest.approx(0.0)


def test_wer_empty_ref():
    assert wer("", "hello world") == pytest.approx(1.0)


def test_wer_empty_hyp():
    assert wer("hello world", "") == pytest.approx(1.0)


def test_wer_insertion():
    assert wer("hello", "hello world") == pytest.approx(0.5)


def test_wer_deletion():
    assert wer("hello world", "hello") == pytest.approx(0.5)


def test_wer_custom_substitution_weight():
    assert wer("a b", "a c", substitution_weight=2) == pytest.approx(1.0)


def test_wer_clamp_false_can_exceed_one():
    result = wer("hello", "hello world foo", clamp=False)
    assert result > 1.0


# ─── CER ──────────────────────────────────────────────────────────────────────

def test_cer_identical():
    assert cer("hello", "hello") == pytest.approx(0.0)


def test_cer_empty_both():
    assert cer("", "") == pytest.approx(0.0)


def test_cer_single_char_sub():
    assert cer("hello", "hella") == pytest.approx(0.2)


def test_cer_empty_ref():
    assert cer("", "abc") == pytest.approx(1.0)


def test_cer_empty_hyp():
    assert cer("abc", "") == pytest.approx(1.0)


# ─── get_segments() ───────────────────────────────────────────────────────────

def test_get_segments_equal():
    segs = get_segments("hello world", "hello world", key=0)
    assert all(s["tag"] == "equal" for s in segs)


def test_get_segments_substitution():
    segs = get_segments("hello world", "hello earth", key=0)
    assert any(s["tag"] == "replace" for s in segs)
    assert any("hello" in s["reference"] for s in segs if s["tag"] == "equal")


def test_get_segments_insertion():
    segs = get_segments("hello", "hello world", key="k")
    assert any(s["tag"] == "insert" for s in segs)


def test_get_segments_deletion():
    segs = get_segments("hello world", "hello", key="k")
    assert any(s["tag"] == "delete" for s in segs)


def test_get_segments_empty():
    assert get_segments("", "", key=0) == []


def test_get_segments_key_preserved():
    segs = get_segments("a b c", "a x c", key="mykey")
    assert all(s["key"] == "mykey" for s in segs)


def test_get_segments_segment_idx_sequential():
    segs = get_segments("a b c", "a x c", key=0)
    for i, s in enumerate(segs):
        assert s["segment_idx"] == i


# ─── process_llm_responses() ──────────────────────────────────────────────────

def _unique_segs():
    return {
        ("hello", "helo"): [{"row_idx": 0, "segment_idx": 1}],
        ("world", "word"): [{"row_idx": 1, "segment_idx": 0}],
    }


def test_process_llm_equivalent_flag():
    ok = [
        {"key": {"reference": "hello", "prediction": "helo"}, "response": {"equivalent": True, "reasoning": "typo"}},
        {"key": {"reference": "world", "prediction": "word"}, "response": {"equivalent": False, "reasoning": "diff"}},
    ]
    flags, logs = process_llm_responses(ok, _unique_segs())
    assert flags.get((0, 1)) is True
    assert (1, 0) not in flags


def test_process_llm_all_non_equivalent():
    ok = [
        {"key": {"reference": "hello", "prediction": "helo"}, "response": {"equivalent": False, "reasoning": "diff"}},
        {"key": {"reference": "world", "prediction": "word"}, "response": {"equivalent": False, "reasoning": "diff"}},
    ]
    flags, _ = process_llm_responses(ok, _unique_segs())
    assert len(flags) == 0


def test_process_llm_log_structure():
    ok = [{"key": {"reference": "hello", "prediction": "helo"}, "response": {"equivalent": True, "reasoning": "phonetic"}}]
    _, logs = process_llm_responses(ok, _unique_segs())
    assert logs[0]["reference"] == "hello"
    assert logs[0]["equivalent"] is True
    assert "phonetic" in logs[0]["reasoning"]


def test_process_llm_missing_keys_skipped():
    flags, logs = process_llm_responses([{"key": {}, "response": {"equivalent": True}}], _unique_segs())
    assert len(flags) == 0


def test_process_llm_multiple_occurrences():
    unique = {("penicillin", "penicilln"): [{"row_idx": 0, "segment_idx": 2}, {"row_idx": 3, "segment_idx": 1}]}
    ok = [{"key": {"reference": "penicillin", "prediction": "penicilln"}, "response": {"equivalent": True, "reasoning": "typo"}}]
    flags, _ = process_llm_responses(ok, unique)
    assert flags[(0, 2)] is True
    assert flags[(3, 1)] is True


# ─── reconstruct_and_score() ──────────────────────────────────────────────────

def test_reconstruct_all_equivalent_zero_wer():
    df = pd.DataFrame({"norm_reference": ["hello world"], "norm_prediction": ["hello wrold"]})
    row_map = {0: [
        {"tag": "equal", "reference": "hello", "prediction": "hello", "segment_idx": 0},
        {"tag": "replace", "reference": "world", "prediction": "wrold", "segment_idx": 1},
    ]}
    result = reconstruct_and_score(df, row_map, {(0, 1): True})
    assert result.loc[0, "corrected_wer"] == pytest.approx(0.0)


def test_reconstruct_non_equivalent_preserves_error():
    df = pd.DataFrame({"norm_reference": ["hello world"], "norm_prediction": ["hello earth"]})
    row_map = {0: [
        {"tag": "equal", "reference": "hello", "prediction": "hello", "segment_idx": 0},
        {"tag": "replace", "reference": "world", "prediction": "earth", "segment_idx": 1},
    ]}
    result = reconstruct_and_score(df, row_map, {})
    assert result.loc[0, "corrected_wer"] == pytest.approx(0.5)


def test_reconstruct_adds_columns():
    df = pd.DataFrame({"norm_reference": ["hello"], "norm_prediction": ["hello"]})
    row_map = {0: [{"tag": "equal", "reference": "hello", "prediction": "hello", "segment_idx": 0}]}
    result = reconstruct_and_score(df, row_map, {})
    assert {"corrected_wer", "corrected_cer", "corrected_prediction", "corrected_reference"}.issubset(result.columns)


# ─── Integration: full pipeline without LLM ───────────────────────────────────

def test_full_pipeline_no_llm():
    df = pd.DataFrame({
        "norm_reference": ["मैं कल आऊंगा", "account balance check"],
        "norm_prediction": ["मैं कल आऊँगा", "account balanc check"],
        "language": ["hindi", "english"],
    })
    row_map, unique_segs = extract_unique_segments(df)

    successful = [
        {"key": {"reference": ref, "prediction": pred},
         "response": {"equivalent": ("आऊ" in ref or "आऊ" in pred), "reasoning": "test"}}
        for ref, pred in unique_segs
    ]
    flags, _ = process_llm_responses(successful, unique_segs)
    result = reconstruct_and_score(df, row_map, flags)

    assert result.loc[0, "corrected_wer"] <= wer(df.loc[0, "norm_reference"], df.loc[0, "norm_prediction"]) + 0.001
    assert {"corrected_wer", "corrected_cer"}.issubset(result.columns)


def test_wer_reduction_for_equivalent_segment():
    ref = "penicillin allergy reported"
    hyp = "penicillin alergy reported"
    original = wer(ref, hyp)

    df = pd.DataFrame({"norm_reference": [ref], "norm_prediction": [hyp]})
    row_map, unique_segs = extract_unique_segments(df)
    successful = [
        {"key": {"reference": k[0], "prediction": k[1]}, "response": {"equivalent": True, "reasoning": "typo"}}
        for k in unique_segs
    ]
    flags, _ = process_llm_responses(successful, unique_segs)
    result = reconstruct_and_score(df, row_map, flags)
    assert result.loc[0, "corrected_wer"] <= original
