"""
WERScorer — LLM-assisted Word/Character Error Rate for Indic ASR evaluation.

Ported from sarvamai/llm_wer and integrated into vyuha.asr.

Pipeline
--------
1. Normalise reference and hypothesis with IndicNormalizer.
2. Compute classical WER / CER (baseline).
3. Diff each pair into word-level segments (SequenceMatcher).
4. For each substituted/inserted/deleted segment, ask an LLM whether the
   two forms are semantically equivalent (spelling variant, phonetic
   reduction, number form, etc.).
5. Reconstruct corrected transcripts where equivalent segments are
   treated as matches, re-score → corrected WER / CER.
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from vyuha.asr.normalizer import wer, cer
from vyuha.asr.llm_client import ChatCompletionsAPI
from pydantic import BaseModel

log = structlog.get_logger()

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "wer_equivalence.txt").read_text()


class _EquivalenceResponse(BaseModel):
    index: int
    equivalent: bool
    reasoning: str


# ── Segment extraction ────────────────────────────────────────────────────────

def get_segments(reference: str, prediction: str, key: Any) -> list[dict]:
    """Diff two strings word-by-word; return SequenceMatcher opcode dicts."""
    try:
        ref_words = reference.strip().split()
        pred_words = prediction.strip().split()
        if not ref_words and not pred_words:
            return []
        matcher = SequenceMatcher(None, ref_words, pred_words)
        return [
            {
                "reference": " ".join(ref_words[i1:i2]),
                "prediction": " ".join(pred_words[j1:j2]),
                "tag": tag,
                "key": key,
                "r_start": i1, "r_end": i2,
                "p_start": j1, "p_end": j2,
                "segment_idx": seg_idx,
            }
            for seg_idx, (tag, i1, i2, j1, j2) in enumerate(matcher.get_opcodes())
        ]
    except Exception as exc:
        log.error("get_segments_error", key=key, error=str(exc))
        return []


def extract_unique_segments(df: pd.DataFrame) -> tuple[dict, dict]:
    """Return (row_segment_map, unique_segments_to_process)."""
    row_map: dict[int, list] = {}
    unique: dict[tuple[str, str], list] = {}
    for idx, row in df.iterrows():
        segs = get_segments(row["norm_reference"], row["norm_prediction"], key=idx)
        row_map[idx] = segs
        for seg in segs:
            if seg["tag"] != "equal" and seg["reference"].strip() and seg["prediction"].strip():
                pair = (seg["reference"], seg["prediction"])
                unique.setdefault(pair, []).append(
                    {"row_idx": idx, "segment_idx": seg["segment_idx"]}
                )
    return row_map, unique


# ── LLM equivalence querying ──────────────────────────────────────────────────

def _build_prompt(seg: dict[str, str]) -> str:
    payload = [{"index": 0, "reference": seg["reference"], "prediction": seg["prediction"]}]
    return _PROMPT_TEMPLATE + "\n\n**INPUT:**\n" + json.dumps(payload, indent=2, ensure_ascii=False)


def query_llm_for_equivalence(
    unique_segments: dict,
    dataset_name: str,
    api: ChatCompletionsAPI,
    cache_dir: Path | None = None,
    ignore_cache: bool = False,
) -> tuple[list, list]:
    cd = (cache_dir or Path("outputs") / "cache")
    cd.mkdir(parents=True, exist_ok=True)
    cache_file = cd / f"{dataset_name}_wer_cache.jsonl"

    if ignore_cache and cache_file.exists():
        cache_file.unlink()

    cached: dict[tuple[str, str], dict] = {}
    if cache_file.exists():
        import jsonlines
        with jsonlines.open(cache_file) as reader:
            for item in reader:
                k = item.get("key", {})
                if "reference" in k and "prediction" in k:
                    cached[(k["reference"], k["prediction"])] = item

    to_query = {p: occ for p, occ in unique_segments.items() if p not in cached}
    from_cache = [v for k, v in cached.items() if k in unique_segments]

    if to_query:
        for ref, pred in to_query:
            api.append_to_request_queue(
                prompt=_build_prompt({"reference": ref, "prediction": pred}),
                key={"reference": ref, "prediction": pred},
                schema=_EquivalenceResponse,
            )
        new_ok, failed = api.generate_responses_from_queue(output_file_path=cache_file)
    else:
        new_ok, failed = [], []

    return from_cache + new_ok, failed


# ── Response processing ───────────────────────────────────────────────────────

def process_llm_responses(
    successful: list, unique_segments: dict
) -> tuple[dict[tuple[int, int], bool], list]:
    verdicts: dict[tuple[str, str], bool] = {}
    logs: list[dict] = []

    for item in successful:
        key = item.get("key", {})
        resp = item.get("response", {})
        if not (key and "reference" in key and "prediction" in key and resp):
            continue
        ref, pred = key["reference"], key["prediction"]
        is_equiv = resp.get("equivalent", False)
        verdicts[(ref, pred)] = is_equiv
        logs.append({"reference": ref, "prediction": pred,
                     "equivalent": is_equiv, "reasoning": resp.get("reasoning", "")})

    flags: dict[tuple[int, int], bool] = {}
    for (ref, pred), occurrences in unique_segments.items():
        if verdicts.get((ref, pred), False):
            for occ in occurrences:
                flags[(occ["row_idx"], occ["segment_idx"])] = True

    return flags, logs


# ── Reconstruction & scoring ──────────────────────────────────────────────────

def reconstruct_and_score(
    df: pd.DataFrame,
    row_segment_map: dict,
    equivalent_flags: dict,
) -> pd.DataFrame:
    corr_preds, corr_refs = [], []
    for idx, row in df.iterrows():
        segs = row_segment_map.get(idx, [])
        pred_parts, ref_parts = [], []
        for seg in segs:
            is_eq = equivalent_flags.get((idx, seg["segment_idx"]), False)
            if seg["tag"] == "equal" or is_eq:
                pred_parts.append(seg["reference"])
                ref_parts.append(seg["reference"])
            else:
                pred_parts.append(seg["prediction"])
                ref_parts.append(seg["reference"])
        corr_preds.append(" ".join(pred_parts))
        corr_refs.append(" ".join(ref_parts))

    df = df.copy()
    df["corrected_prediction"] = corr_preds
    df["corrected_reference"] = corr_refs
    df["corrected_wer"] = [wer(r, p) for r, p in zip(df["corrected_reference"], df["corrected_prediction"])]
    df["corrected_cer"] = [cer(r, p) for r, p in zip(df["corrected_reference"], df["corrected_prediction"])]
    return df


# ── Top-level scorer ──────────────────────────────────────────────────────────

class WERScorer:
    """
    High-level interface for LLM-assisted WER/CER scoring.

    Usage::

        scorer = WERScorer(api)
        result_df = scorer.score(df, ref_col="transcription",
                                 pred_col="prediction", lang_col="language")
        print(result_df[["original_wer", "corrected_wer"]].mean())
    """

    def __init__(self, api: ChatCompletionsAPI | None = None) -> None:
        self._api = api

    def score(
        self,
        df: pd.DataFrame,
        ref_col: str = "transcription",
        pred_col: str = "prediction",
        lang_col: str = "language",
        dataset_name: str = "dataset",
        cache_dir: Path | None = None,
        ignore_cache: bool = False,
        normalizer=None,
    ) -> pd.DataFrame:
        """
        Run the full WER pipeline. Returns df with added columns:
        norm_reference, norm_prediction, original_wer, original_cer,
        corrected_wer, corrected_cer.
        """
        # 1. Normalise
        if normalizer is not None:
            df = df.copy()
            df["norm_reference"] = normalizer.normalize_texts(
                df[ref_col].astype(str).tolist(), df[lang_col].astype(str).tolist()
            )
            df["norm_prediction"] = normalizer.normalize_texts(
                df[pred_col].astype(str).tolist(), df[lang_col].astype(str).tolist()
            )
        else:
            df = df.copy()
            df["norm_reference"] = df[ref_col]
            df["norm_prediction"] = df[pred_col]

        # 2. Baseline
        df["original_wer"] = [wer(r, p) for r, p in zip(df["norm_reference"], df["norm_prediction"])]
        df["original_cer"] = [cer(r, p) for r, p in zip(df["norm_reference"], df["norm_prediction"])]

        if self._api is None:
            # No LLM — return classical scores only
            return df

        # 3. Segment & query
        row_map, unique_segs = extract_unique_segments(df)
        successful, _ = query_llm_for_equivalence(
            unique_segs, dataset_name, self._api, cache_dir, ignore_cache
        )
        flags, _ = process_llm_responses(successful, unique_segs)

        # 4. Reconstruct
        return reconstruct_and_score(df, row_map, flags)
