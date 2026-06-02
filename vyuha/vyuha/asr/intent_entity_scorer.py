"""
IntentEntityScorer — LLM-as-Judge intent and entity accuracy for ASR output.

Ported from sarvamai/llm_intent_entity and integrated into vyuha.asr.

Pipeline
--------
1. Normalise hypothesis and ground-truth with IndicNormalizer.
2. For each row, send (hypothesis, ground_truth, context) to an LLM judge
   with a detailed Indic-language rubric (see prompts/intent_entity.txt).
3. Collect intent_score (0/1) and entity_score (0–1) per row.
4. Aggregate: intent_accuracy, entity mean/median/std.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from vyuha.asr.normalizer import calculate_intent_accuracy, calculate_entity_metrics
from vyuha.asr.llm_client import ChatCompletionsAPI
from pydantic import BaseModel

log = structlog.get_logger()

_PROMPT_TEMPLATE = (
    Path(__file__).parent / "prompts" / "intent_entity.txt"
).read_text()


class _IntentEntityResponse(BaseModel):
    index: int
    intent_score: int
    intent_explanation: str
    entity_score: float
    ground_truth_entities: str
    preserved_entities: str
    missing_entities: str
    entity_explanation: str


# ── Prompt building ───────────────────────────────────────────────────────────

def build_prompt(item: dict[str, Any]) -> str:
    payload = {
        "index": item["index"],
        "hypothesis": item["hypothesis"],
        "ground_truth": item["ground_truth"],
        "context": item.get("context", ""),
    }
    return _PROMPT_TEMPLATE + "\n\n**INPUT:**\n" + json.dumps(payload, indent=2, ensure_ascii=False)


# ── Dataset helpers ───────────────────────────────────────────────────────────

def load_and_validate_dataset(path: str, required_cols: set) -> pd.DataFrame:
    from pathlib import Path as P
    p = P(path)
    if not p.exists():
        raise FileNotFoundError(f"{path} does not exist")
    suf = p.suffix.lower()
    if suf == ".csv":
        df = pd.read_csv(p)
    elif suf in {".jsonl", ".json"}:
        df = pd.read_json(p, lines=True)
    else:
        raise ValueError("Unsupported dataset format. Only CSV or JSONL accepted.")
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in dataset: {', '.join(missing)}")
    return df


def prepare_evaluation_items(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "index": idx,
            "hypothesis": row["norm_prediction"],
            "ground_truth": row["norm_reference"],
            "context": row.get("context", ""),
        }
        for idx, row in df.iterrows()
    ]


# ── LLM querying ─────────────────────────────────────────────────────────────

def query_llm_for_intent_entity(
    items: list[dict],
    dataset_name: str,
    api: ChatCompletionsAPI,
    cache_dir: Path | None = None,
    ignore_cache: bool = False,
) -> tuple[list, list]:
    cd = cache_dir or Path("outputs") / "cache"
    cd.mkdir(parents=True, exist_ok=True)
    cache_file = cd / f"{dataset_name}_intent_entity_cache.jsonl"

    if ignore_cache and cache_file.exists():
        cache_file.unlink()

    cached: dict[tuple[str, str, str], dict] = {}
    if cache_file.exists():
        import jsonlines
        with jsonlines.open(cache_file) as reader:
            for entry in reader:
                k = entry.get("key", {})
                if "index" in k:
                    ck = (k.get("hypothesis", ""), k.get("ground_truth", ""), k.get("context", ""))
                    cached[ck] = entry

    to_query = [
        it for it in items
        if (it["hypothesis"], it["ground_truth"], it.get("context", "")) not in cached
    ]
    from_cache = [
        v for ck, v in cached.items()
        if any(
            (it["hypothesis"], it["ground_truth"], it.get("context", "")) == ck
            for it in items
        )
    ]

    if to_query:
        for it in to_query:
            api.append_to_request_queue(
                prompt=build_prompt(it),
                key=it,
                schema=_IntentEntityResponse,
            )
        new_ok, failed = api.generate_responses_from_queue(output_file_path=cache_file)
    else:
        new_ok, failed = [], []

    return from_cache + new_ok, failed


# ── Response processing ───────────────────────────────────────────────────────

def process_llm_responses(successful: list, df: pd.DataFrame) -> pd.DataFrame:
    resp_map: dict[int, dict] = {}
    for item in successful:
        key = item.get("key", {})
        resp = item.get("response", {})
        if key and "index" in key:
            resp_map[key["index"]] = resp

    ERROR = -1
    cols: dict[str, list] = {
        "intent_score": [], "intent_explanation": [],
        "entity_score": [], "ground_truth_entities": [],
        "preserved_entities": [], "missing_entities": [], "entity_explanation": [],
    }
    for idx in df.index:
        r = resp_map.get(idx)
        if r:
            cols["intent_score"].append(r.get("intent_score", ERROR))
            cols["intent_explanation"].append(r.get("intent_explanation", ""))
            cols["entity_score"].append(r.get("entity_score", float(ERROR)))
            cols["ground_truth_entities"].append(r.get("ground_truth_entities", ""))
            cols["preserved_entities"].append(r.get("preserved_entities", ""))
            cols["missing_entities"].append(r.get("missing_entities", ""))
            cols["entity_explanation"].append(r.get("entity_explanation", ""))
        else:
            cols["intent_score"].append(ERROR)
            cols["intent_explanation"].append("ERROR: No response")
            cols["entity_score"].append(float(ERROR))
            cols["ground_truth_entities"].append("ERROR")
            cols["preserved_entities"].append("ERROR")
            cols["missing_entities"].append("ERROR")
            cols["entity_explanation"].append("ERROR: No response")

    df = df.copy()
    for col, vals in cols.items():
        df[col] = vals
    return df


# ── Metrics ───────────────────────────────────────────────────────────────────

def calculate_metrics(df: pd.DataFrame) -> dict:
    valid = df[(df["intent_score"] >= 0) & (df["entity_score"] >= 0)]
    if len(valid) == 0:
        return {
            "total_samples": len(df), "valid_samples": 0,
            "intent_accuracy": 0.0,
            "entity_metrics": {"mean": 0.0, "median": 0.0, "std": 0.0},
        }
    return {
        "total_samples": len(df),
        "valid_samples": len(valid),
        "intent_accuracy": calculate_intent_accuracy(valid["intent_score"].tolist()),
        "entity_metrics": calculate_entity_metrics(valid["entity_score"].tolist()),
    }


# ── Top-level scorer ──────────────────────────────────────────────────────────

class IntentEntityScorer:
    """
    High-level interface for LLM-as-Judge intent + entity scoring.

    Usage::

        scorer = IntentEntityScorer(api)
        df, metrics = scorer.score(df, ref_col="transcription",
                                   pred_col="prediction", lang_col="language")
        print(metrics["intent_accuracy"])
    """

    def __init__(self, api: ChatCompletionsAPI) -> None:
        self._api = api

    def score(
        self,
        df: pd.DataFrame,
        ref_col: str = "transcription",
        pred_col: str = "prediction",
        lang_col: str = "language",
        context_col: str = "context",
        dataset_name: str = "dataset",
        cache_dir: Path | None = None,
        ignore_cache: bool = False,
        normalizer=None,
    ) -> tuple[pd.DataFrame, dict]:
        """
        Run the full intent/entity pipeline.

        Returns (result_df, metrics_dict).
        result_df has: norm_reference, norm_prediction,
            intent_score, intent_explanation, entity_score,
            ground_truth_entities, preserved_entities, missing_entities.
        """
        df = df.copy()

        if context_col not in df.columns:
            df[context_col] = ""

        if normalizer is not None:
            df["norm_reference"] = normalizer.normalize_texts(
                df[ref_col].astype(str).tolist(), df[lang_col].astype(str).tolist()
            )
            df["norm_prediction"] = normalizer.normalize_texts(
                df[pred_col].astype(str).tolist(), df[lang_col].astype(str).tolist()
            )
        else:
            df["norm_reference"] = df[ref_col]
            df["norm_prediction"] = df[pred_col]

        items = prepare_evaluation_items(df)
        successful, failed = query_llm_for_intent_entity(
            items, dataset_name, self._api, cache_dir, ignore_cache
        )
        if failed:
            log.warning("intent_entity_failed_requests", count=len(failed))

        df = process_llm_responses(successful, df)
        metrics = calculate_metrics(df)
        return df, metrics
