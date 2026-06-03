"""Retrieval / RAG evaluators: Recall@K, Precision@K, NDCG@K, MRR, HitRate."""
from __future__ import annotations

import math
from typing import Any
from vyuha.evaluators.base import BaseEvaluator, EvalResult


def _as_lists(retrieved: Any, relevant: Any) -> tuple[list, list]:
    """Normalise single query or list-of-queries to flat lists."""
    if isinstance(retrieved[0], list):
        retrieved = [item for sub in retrieved for item in sub]
    if isinstance(relevant[0], list):
        relevant = [item for sub in relevant for item in sub]
    return list(retrieved), list(relevant)


class RecallAtK(BaseEvaluator):
    """Recall@K = |retrieved[:k] ∩ relevant| / |relevant|"""
    name = "recall_at_k"
    description = "Fraction of relevant items found in top-K results."
    required_keys = ["retrieved", "relevant"]

    def __init__(self, k: int = 5, pass_threshold: float | None = 0.8) -> None:
        self.k = k
        self.pass_threshold = pass_threshold

    def _evaluate(self, retrieved: list, relevant: list, **_: Any) -> EvalResult:
        r, rel = _as_lists(retrieved, relevant)
        if not rel:
            return EvalResult(value=1.0, reason="No relevant items — trivially 1.")
        top_k = set(r[:self.k])
        hits = len(top_k & set(rel))
        score = round(hits / len(rel), 4)
        return EvalResult(value=score, reason=f"Recall@{self.k}: {score} ({hits}/{len(rel)})")


class PrecisionAtK(BaseEvaluator):
    """Precision@K = |retrieved[:k] ∩ relevant| / k"""
    name = "precision_at_k"
    description = "Fraction of top-K results that are relevant."
    required_keys = ["retrieved", "relevant"]

    def __init__(self, k: int = 5, pass_threshold: float | None = 0.5) -> None:
        self.k = k
        self.pass_threshold = pass_threshold

    def _evaluate(self, retrieved: list, relevant: list, **_: Any) -> EvalResult:
        r, rel = _as_lists(retrieved, relevant)
        top_k = r[:self.k]
        hits = sum(1 for x in top_k if x in set(rel))
        score = round(hits / max(self.k, 1), 4)
        return EvalResult(value=score, reason=f"Precision@{self.k}: {score} ({hits}/{self.k})")


class NdcgAtK(BaseEvaluator):
    """NDCG@K with binary relevance."""
    name = "ndcg_at_k"
    description = "Normalised Discounted Cumulative Gain at K."
    required_keys = ["retrieved", "relevant"]

    def __init__(self, k: int = 5, pass_threshold: float | None = 0.7) -> None:
        self.k = k
        self.pass_threshold = pass_threshold

    def _evaluate(self, retrieved: list, relevant: list, **_: Any) -> EvalResult:
        r, rel = _as_lists(retrieved, relevant)
        rel_set = set(rel)
        dcg = sum(
            (1.0 / math.log2(i + 2)) for i, x in enumerate(r[:self.k]) if x in rel_set
        )
        ideal = sum(
            (1.0 / math.log2(i + 2)) for i in range(min(len(rel_set), self.k))
        )
        score = round(dcg / ideal, 4) if ideal > 0 else 0.0
        return EvalResult(value=score, reason=f"NDCG@{self.k}: {score}")


class MeanReciprocalRank(BaseEvaluator):
    """MRR = mean of 1/rank of first relevant result."""
    name = "mean_reciprocal_rank"
    description = "Mean Reciprocal Rank of first relevant result."
    required_keys = ["retrieved", "relevant"]

    def _evaluate(self, retrieved: list, relevant: list, **_: Any) -> EvalResult:
        r, rel = _as_lists(retrieved, relevant)
        rel_set = set(rel)
        for i, x in enumerate(r):
            if x in rel_set:
                mrr = round(1.0 / (i + 1), 4)
                return EvalResult(value=mrr, reason=f"First relevant at rank {i+1} → MRR={mrr}")
        return EvalResult(value=0.0, reason="No relevant item found in retrieved list.")


class HitRate(BaseEvaluator):
    """HitRate@K = 1 if any relevant item in top-K, else 0."""
    name = "hit_rate"
    description = "1 if any relevant item appears in top-K results."
    required_keys = ["retrieved", "relevant"]

    def __init__(self, k: int = 5) -> None:
        self.k = k
        self.pass_threshold = 1.0

    def _evaluate(self, retrieved: list, relevant: list, **_: Any) -> EvalResult:
        r, rel = _as_lists(retrieved, relevant)
        hit = any(x in set(rel) for x in r[:self.k])
        return EvalResult(value=1.0 if hit else 0.0, reason=f"Hit@{self.k}: {'yes' if hit else 'no'}", passed=hit)
