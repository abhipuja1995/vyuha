"""
Indic text normalisation and classical WER/CER metrics.

Ported from sarvamai/llm_wer and sarvamai/llm_intent_entity.
IndicNormalizer requires: indicnlp, transformers (Whisper tokenizer)
wer/cer require: jiwer
"""
from __future__ import annotations

import re
import string
from typing import List, Tuple

import jiwer

# ── Language code lookup ──────────────────────────────────────────────────────

LANG_TO_CODE: dict[str, str] = {
    "hindi": "hi", "bengali": "bn", "tamil": "ta", "telugu": "te",
    "gujarati": "gu", "kannada": "kn", "malayalam": "ml", "marathi": "mr",
    "odia": "or", "oria": "or", "assamese": "or", "punjabi": "pa",
    "english": "en",
}

INDIC_LANGS = {"hi", "bn", "ta", "te", "gu", "kn", "ml", "mr", "or", "pa"}

INDIC_PUNCTUATION = (
    "।॥॰''\"‛‟′″´˝^°¤।॥॰¯'—–‑°¬´ۭ۪​‌‍‎‏"
)


# ── WER / CER ─────────────────────────────────────────────────────────────────

def wer(
    ref: str,
    hyp: str,
    clamp: bool = True,
    insertion_weight: float = 1.0,
    deletion_weight: float = 1.0,
    substitution_weight: float = 1.0,
) -> float:
    """Word Error Rate with optional clamping and custom weights."""
    ref, hyp = str(ref).strip(), str(hyp).strip()
    N, M = len(ref.split()), len(hyp.split())
    if N == 0 and M == 0:
        return 0.0
    if N == 0:
        return insertion_weight
    if M == 0:
        return deletion_weight
    out = jiwer.process_words(ref, hyp)
    denom = max(M, N) if clamp else N
    return (
        out.substitutions * substitution_weight
        + out.deletions * deletion_weight
        + out.insertions * insertion_weight
    ) / denom


def cer(
    ref: str,
    hyp: str,
    clamp: bool = True,
    insertion_weight: float = 1.0,
    deletion_weight: float = 1.0,
    substitution_weight: float = 1.0,
) -> float:
    """Character Error Rate with optional clamping and custom weights."""
    ref, hyp = str(ref).strip(), str(hyp).strip()
    N, M = len(ref), len(hyp)
    if N == 0 and M == 0:
        return 0.0
    if N == 0:
        return insertion_weight
    if M == 0:
        return deletion_weight
    out = jiwer.process_characters(ref, hyp)
    denom = max(M, N) if clamp else N
    return (
        out.substitutions * substitution_weight
        + out.deletions * deletion_weight
        + out.insertions * insertion_weight
    ) / denom


# ── IndicNormalizer ───────────────────────────────────────────────────────────

class IndicNormalizer:
    """
    Normalises Indic and English text for fair WER/CER comparison.
    Requires: indicnlp, transformers (loaded lazily).
    """

    def __init__(self) -> None:
        from indicnlp.normalize.indic_normalize import IndicNormalizerFactory
        from transformers import WhisperProcessor
        self._factory = IndicNormalizerFactory()
        processor = WhisperProcessor.from_pretrained("openai/whisper-small")
        self._whisper_tok = processor.tokenizer

    def normalize_text(self, text: str, lang_code: str) -> str:
        import pandas as pd
        lang_code = LANG_TO_CODE.get(lang_code, lang_code)
        if pd.isna(text) or not isinstance(text, str) or not text:
            return text
        base = lang_code.split("-")[0].lower()
        text = re.sub(r"([,\-\.\(\)\[\]\{\}/\\])\B", r" ", text)
        text = text.translate(
            str.maketrans("", "", string.punctuation + INDIC_PUNCTUATION)
        ).lower()
        if base in INDIC_LANGS and base != "ur":
            text = self._factory.get_normalizer(base).normalize(text)
        else:
            text = self._whisper_tok.normalize(text)
        return re.sub(r" +", " ", text).strip()

    def normalize_texts(
        self,
        text_list: List[str],
        lang_list: List[str],
        n_jobs: int = -1,
        batch_size: int = 500,
    ) -> List[str]:
        from joblib import Parallel, delayed
        from tqdm import tqdm
        if len(text_list) != len(lang_list):
            raise ValueError("text_list and lang_list must have the same length")
        if not text_list:
            return []
        batches: List[Tuple[List[str], List[str]]] = [
            (text_list[i : i + batch_size], lang_list[i : i + batch_size])
            for i in range(0, len(text_list), batch_size)
        ]

        def _batch(texts: List[str], langs: List[str]) -> List[str]:
            return [self.normalize_text(t, l) for t, l in zip(texts, langs)]

        results = Parallel(n_jobs=n_jobs)(
            delayed(_batch)(tb, lb)
            for tb, lb in tqdm(batches, desc="Normalising")
        )
        return [item for sub in results for item in sub]  # type: ignore


# ── Intent / entity metric helpers ───────────────────────────────────────────

def calculate_intent_accuracy(scores: List[int]) -> float:
    """Mean of binary intent scores (0 or 1)."""
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def calculate_entity_metrics(scores: List[float]) -> dict:
    """Mean, median and std of entity scores (0–1)."""
    import numpy as np
    if not scores:
        return {"mean": 0.0, "median": 0.0, "std": 0.0}
    arr = np.array(scores)
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
    }
