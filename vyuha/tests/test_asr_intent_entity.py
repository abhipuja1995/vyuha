"""
Tests for vyuha.asr.intent_entity_scorer (43 tests) — no LLM API required.

Covers: calculate_intent_accuracy(), calculate_entity_metrics(),
build_prompt(), load_and_validate_dataset(), prepare_evaluation_items(),
process_llm_responses(), calculate_metrics(), and Indic language scenarios.

Ported from sarvamai/llm_intent_entity and re-homed inside vyuha.
"""
from __future__ import annotations

import json
import os
import tempfile

import pandas as pd
import pytest

from vyuha.asr.normalizer import calculate_intent_accuracy, calculate_entity_metrics
from vyuha.asr.intent_entity_scorer import (
    build_prompt,
    load_and_validate_dataset,
    prepare_evaluation_items,
    process_llm_responses,
    calculate_metrics,
)


# ─── calculate_intent_accuracy() ─────────────────────────────────────────────

def test_intent_accuracy_all_correct():
    assert calculate_intent_accuracy([1, 1, 1, 1]) == pytest.approx(1.0)


def test_intent_accuracy_all_wrong():
    assert calculate_intent_accuracy([0, 0, 0]) == pytest.approx(0.0)


def test_intent_accuracy_mixed():
    assert calculate_intent_accuracy([1, 1, 0, 1]) == pytest.approx(0.75)


def test_intent_accuracy_empty():
    assert calculate_intent_accuracy([]) == pytest.approx(0.0)


def test_intent_accuracy_single_correct():
    assert calculate_intent_accuracy([1]) == pytest.approx(1.0)


def test_intent_accuracy_single_wrong():
    assert calculate_intent_accuracy([0]) == pytest.approx(0.0)


# ─── calculate_entity_metrics() ──────────────────────────────────────────────

def test_entity_metrics_perfect():
    r = calculate_entity_metrics([1.0, 1.0, 1.0])
    assert r["mean"] == pytest.approx(1.0)
    assert r["std"] == pytest.approx(0.0)


def test_entity_metrics_zero():
    r = calculate_entity_metrics([0.0, 0.0])
    assert r["mean"] == pytest.approx(0.0)


def test_entity_metrics_mixed():
    r = calculate_entity_metrics([0.0, 0.5, 1.0])
    assert r["mean"] == pytest.approx(0.5)
    assert r["median"] == pytest.approx(0.5)
    assert r["std"] > 0


def test_entity_metrics_empty():
    assert calculate_entity_metrics([]) == {"mean": 0.0, "median": 0.0, "std": 0.0}


def test_entity_metrics_single():
    r = calculate_entity_metrics([0.7])
    assert r["mean"] == pytest.approx(0.7)
    assert r["std"] == pytest.approx(0.0)


def test_entity_metrics_keys():
    assert set(calculate_entity_metrics([0.5]).keys()) == {"mean", "median", "std"}


# ─── build_prompt() ──────────────────────────────────────────────────────────

def test_build_prompt_contains_hypothesis():
    item = {"index": 0, "hypothesis": "Mujhe appointment book karni hai", "ground_truth": "Book appointment", "context": ""}
    assert "Mujhe appointment book karni hai" in build_prompt(item)


def test_build_prompt_contains_ground_truth():
    item = {"index": 0, "hypothesis": "Balance batao", "ground_truth": "Check account balance", "context": ""}
    assert "Check account balance" in build_prompt(item)


def test_build_prompt_contains_context():
    item = {"index": 0, "hypothesis": "help", "ground_truth": "help", "context": "Customer support"}
    assert "Customer support" in build_prompt(item)


def test_build_prompt_contains_index():
    item = {"index": 42, "hypothesis": "hello", "ground_truth": "hello", "context": ""}
    assert "42" in build_prompt(item)


def test_build_prompt_valid_json_embedded():
    item = {"index": 0, "hypothesis": "test hyp", "ground_truth": "test gt", "context": "ctx"}
    prompt = build_prompt(item)
    parsed = json.loads(prompt.split("**INPUT:**")[-1].strip())
    assert parsed["hypothesis"] == "test hyp"
    assert parsed["ground_truth"] == "test gt"


def test_build_prompt_missing_context_defaults_empty():
    item = {"index": 0, "hypothesis": "test", "ground_truth": "gt"}
    parsed = json.loads(build_prompt(item).split("**INPUT:**")[-1].strip())
    assert parsed["context"] == ""


# ─── load_and_validate_dataset() ─────────────────────────────────────────────

def test_load_csv_valid():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("transcription,prediction,audio_filepath,language\n")
        f.write("ek sau rupye,ek so rupye,/audio/1.wav,hindi\n")
        fname = f.name
    try:
        df = load_and_validate_dataset(fname, {"transcription", "prediction", "audio_filepath", "language"})
        assert len(df) == 1
    finally:
        os.unlink(fname)


def test_load_jsonl_valid():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps({"transcription": "hi", "prediction": "hi", "audio_filepath": "/a.wav", "language": "english"}) + "\n")
        fname = f.name
    try:
        df = load_and_validate_dataset(fname, {"transcription", "prediction", "audio_filepath", "language"})
        assert len(df) == 1
    finally:
        os.unlink(fname)


def test_load_missing_column_raises():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("transcription,prediction\nhello,helo\n")
        fname = f.name
    try:
        with pytest.raises(ValueError, match="Missing columns"):
            load_and_validate_dataset(fname, {"transcription", "prediction", "audio_filepath", "language"})
    finally:
        os.unlink(fname)


def test_load_nonexistent_raises():
    with pytest.raises(FileNotFoundError):
        load_and_validate_dataset("/does/not/exist.csv", {"transcription"})


def test_load_unsupported_format_raises():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".parquet", delete=False) as f:
        f.write("data\n")
        fname = f.name
    try:
        with pytest.raises(ValueError, match="Unsupported"):
            load_and_validate_dataset(fname, {"transcription"})
    finally:
        os.unlink(fname)


# ─── prepare_evaluation_items() ──────────────────────────────────────────────

def test_prepare_items_basic():
    df = pd.DataFrame({"norm_prediction": ["help chahiye", "balance batao"], "norm_reference": ["I need help", "check balance"]})
    items = prepare_evaluation_items(df)
    assert len(items) == 2
    assert items[0]["hypothesis"] == "help chahiye"
    assert items[0]["ground_truth"] == "I need help"


def test_prepare_items_includes_context():
    df = pd.DataFrame({"norm_prediction": ["yes"], "norm_reference": ["yes"], "context": ["Banking IVR"]})
    assert prepare_evaluation_items(df)[0]["context"] == "Banking IVR"


def test_prepare_items_empty_context_when_missing():
    df = pd.DataFrame({"norm_prediction": ["hello"], "norm_reference": ["hello"]})
    assert prepare_evaluation_items(df)[0]["context"] == ""


def test_prepare_items_index_alignment():
    df = pd.DataFrame({"norm_prediction": ["a", "b", "c"], "norm_reference": ["a", "b", "c"]})
    for item, idx in zip(prepare_evaluation_items(df), df.index):
        assert item["index"] == idx


# ─── process_llm_responses() ─────────────────────────────────────────────────

def _two_row_df():
    return pd.DataFrame({"norm_prediction": ["pred_0", "pred_1"], "norm_reference": ["ref_0", "ref_1"]}, index=[0, 1])


def test_process_fills_scores():
    df = _two_row_df()
    ok = [
        {"key": {"index": 0, "hypothesis": "pred_0", "ground_truth": "ref_0", "context": ""},
         "response": {"intent_score": 1, "intent_explanation": "ok", "entity_score": 0.9,
                      "ground_truth_entities": "balance", "preserved_entities": "balance",
                      "missing_entities": "", "entity_explanation": "all present"}},
        {"key": {"index": 1, "hypothesis": "pred_1", "ground_truth": "ref_1", "context": ""},
         "response": {"intent_score": 0, "intent_explanation": "wrong pronoun", "entity_score": 0.5,
                      "ground_truth_entities": "name, amount", "preserved_entities": "name",
                      "missing_entities": "amount", "entity_explanation": "partial"}},
    ]
    result = process_llm_responses(ok, df)
    assert result.loc[0, "intent_score"] == 1
    assert result.loc[0, "entity_score"] == pytest.approx(0.9)
    assert result.loc[1, "intent_score"] == 0
    assert result.loc[1, "entity_score"] == pytest.approx(0.5)


def test_process_missing_fills_error_sentinel():
    result = process_llm_responses([], _two_row_df())
    assert result.loc[0, "intent_score"] == -1
    assert result.loc[0, "entity_score"] == pytest.approx(-1.0)
    assert "ERROR" in result.loc[0, "intent_explanation"]


def test_process_partial_coverage():
    df = _two_row_df()
    ok = [{"key": {"index": 0, "hypothesis": "pred_0", "ground_truth": "ref_0", "context": ""},
           "response": {"intent_score": 1, "intent_explanation": "ok", "entity_score": 1.0,
                        "ground_truth_entities": "x", "preserved_entities": "x",
                        "missing_entities": "", "entity_explanation": "all"}}]
    result = process_llm_responses(ok, df)
    assert result.loc[0, "intent_score"] == 1
    assert result.loc[1, "intent_score"] == -1


# ─── calculate_metrics() ─────────────────────────────────────────────────────

def test_metrics_all_valid():
    df = pd.DataFrame({"intent_score": [1, 0, 1, 1], "entity_score": [1.0, 0.5, 0.8, 1.0]})
    r = calculate_metrics(df)
    assert r["total_samples"] == 4
    assert r["valid_samples"] == 4
    assert r["intent_accuracy"] == pytest.approx(0.75)
    assert r["entity_metrics"]["mean"] == pytest.approx(0.825)


def test_metrics_filters_sentinels():
    df = pd.DataFrame({"intent_score": [1, -1, 0], "entity_score": [0.9, -1.0, 0.5]})
    r = calculate_metrics(df)
    assert r["total_samples"] == 3
    assert r["valid_samples"] == 2
    assert r["intent_accuracy"] == pytest.approx(0.5)


def test_metrics_all_errors():
    df = pd.DataFrame({"intent_score": [-1, -1], "entity_score": [-1.0, -1.0]})
    r = calculate_metrics(df)
    assert r["valid_samples"] == 0
    assert r["intent_accuracy"] == pytest.approx(0.0)


def test_metrics_required_keys():
    df = pd.DataFrame({"intent_score": [1], "entity_score": [1.0]})
    assert {"total_samples", "valid_samples", "intent_accuracy", "entity_metrics"}.issubset(calculate_metrics(df))


# ─── Parameterised Indic language scenarios ───────────────────────────────────

@pytest.mark.parametrize("scores,expected", [
    ([1], 1.0),           # Telugu allergy — intent preserved
    ([0], 0.0),           # Tamil emergency — agent failed to escalate
    ([1, 1, 0], pytest.approx(2 / 3)),  # Hindi mixed
    ([1, 0, 1, 1], 0.75),              # Odia noisy outdoor
])
def test_intent_accuracy_indic_scenarios(scores, expected):
    assert calculate_intent_accuracy(scores) == expected


@pytest.mark.parametrize("hypothesis,ground_truth,has_context", [
    ("Nenu okka allergy report cheyyali", "I need to report an allergy", True),
    ("Ennaku ippo marbaga vali irukku", "I have chest pain right now", False),
    ("En outstanding amount enna", "What is my outstanding amount", True),
    ("Mora account balance kana", "What is my account balance", True),
    ("mujhe appointment book karni hai", "Book an appointment for Monday", True),
])
def test_build_prompt_indic_utterances(hypothesis, ground_truth, has_context):
    item = {"index": 0, "hypothesis": hypothesis, "ground_truth": ground_truth,
            "context": "Voice AI evaluation" if has_context else ""}
    prompt = build_prompt(item)
    assert hypothesis in prompt
    assert ground_truth in prompt
    assert len(prompt) > 100
