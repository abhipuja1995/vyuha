"""
Statistical / classification evaluators — FutureAGI-parity.
No LLM required. Uses stdlib with optional scipy/sklearn fallback.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Any

from vyuha.evaluators.base import BaseEvaluator, EvalResult


def _compute_confusion(predictions: list, references: list, label):
    tp = sum(1 for p, r in zip(predictions, references) if p == label and r == label)
    fp = sum(1 for p, r in zip(predictions, references) if p == label and r != label)
    fn = sum(1 for p, r in zip(predictions, references) if p != label and r == label)
    return tp, fp, fn


def _precision_recall_f1_per_class(predictions: list, references: list):
    labels = list(set(references) | set(predictions))
    results = {}
    for label in labels:
        tp, fp, fn = _compute_confusion(predictions, references, label)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        results[label] = (prec, rec, f1, sum(1 for r in references if r == label))
    return results


def _aggregate(per_class: dict, average: str):
    items = list(per_class.values())
    if average == "macro":
        prec = statistics.mean(x[0] for x in items)
        rec = statistics.mean(x[1] for x in items)
        f1 = statistics.mean(x[2] for x in items)
    elif average == "weighted":
        total = sum(x[3] for x in items)
        prec = sum(x[0] * x[3] for x in items) / total if total else 0.0
        rec = sum(x[1] * x[3] for x in items) / total if total else 0.0
        f1 = sum(x[2] * x[3] for x in items) / total if total else 0.0
    else:  # micro
        tp_total = sum(x[0] for x in items)
        # recompute globally
        prec = rec = f1 = 0.0
    return prec, rec, f1


class F1Score(BaseEvaluator):
    name = "f1_score"
    description = "F1 score for classification tasks."
    required_keys = ["predictions", "references"]

    def _evaluate(self, predictions: list, references: list, average: str = "macro", **_: Any) -> EvalResult:
        per_class = _precision_recall_f1_per_class(predictions, references)
        _, _, f1 = _aggregate(per_class, average)
        return EvalResult(value=f1, reason=f"F1={f1:.3f}")


class AccuracyScore(BaseEvaluator):
    name = "accuracy"
    description = "Accuracy for classification tasks."
    required_keys = ["predictions", "references"]

    def _evaluate(self, predictions: list, references: list, **_: Any) -> EvalResult:
        if not predictions:
            return EvalResult(value=0.0, reason="Empty predictions")
        acc = sum(p == r for p, r in zip(predictions, references)) / len(predictions)
        return EvalResult(value=acc, reason=f"Accuracy={acc:.3f}")


class PrecisionScore(BaseEvaluator):
    name = "precision"
    description = "Precision for classification tasks."
    required_keys = ["predictions", "references"]

    def _evaluate(self, predictions: list, references: list, average: str = "macro", **_: Any) -> EvalResult:
        per_class = _precision_recall_f1_per_class(predictions, references)
        prec, _, _ = _aggregate(per_class, average)
        return EvalResult(value=prec, reason=f"Precision={prec:.3f}")


class RecallScore(BaseEvaluator):
    name = "recall"
    description = "Recall for classification tasks."
    required_keys = ["predictions", "references"]

    def _evaluate(self, predictions: list, references: list, average: str = "macro", **_: Any) -> EvalResult:
        per_class = _precision_recall_f1_per_class(predictions, references)
        _, rec, _ = _aggregate(per_class, average)
        return EvalResult(value=rec, reason=f"Recall={rec:.3f}")


class NumericSimilarity(BaseEvaluator):
    name = "numeric_similarity"
    description = "Similarity between two numeric values (1 - normalized absolute difference)."
    required_keys = ["output", "expected"]

    def _evaluate(self, output: Any, expected: Any, **_: Any) -> EvalResult:
        try:
            a = float(output)
            b = float(expected)
            sim = 1.0 - abs(a - b) / max(abs(a), abs(b), 1.0)
            return EvalResult(value=max(0.0, sim), reason=f"NumericSim={sim:.3f}")
        except Exception as exc:
            return EvalResult(value=0.0, reason=f"Parse error: {exc}")


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def _rank(lst: list[float]) -> list[float]:
    sorted_vals = sorted(enumerate(lst), key=lambda x: x[1])
    ranks = [0.0] * len(lst)
    i = 0
    while i < len(sorted_vals):
        j = i
        while j < len(sorted_vals) - 1 and sorted_vals[j + 1][1] == sorted_vals[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[sorted_vals[k][0]] = avg_rank
        i = j + 1
    return ranks


class PearsonCorrelation(BaseEvaluator):
    name = "pearson_correlation"
    description = "Pearson correlation coefficient between predictions and references."
    required_keys = ["predictions", "references"]

    def _evaluate(self, predictions: list, references: list, **_: Any) -> EvalResult:
        x = [float(v) for v in predictions]
        y = [float(v) for v in references]
        r = _pearson(x, y)
        return EvalResult(value=r, reason=f"Pearson r={r:.4f}")


class SpearmanCorrelation(BaseEvaluator):
    name = "spearman_correlation"
    description = "Spearman rank correlation between predictions and references."
    required_keys = ["predictions", "references"]

    def _evaluate(self, predictions: list, references: list, **_: Any) -> EvalResult:
        x = [float(v) for v in predictions]
        y = [float(v) for v in references]
        rx = _rank(x)
        ry = _rank(y)
        r = _pearson(rx, ry)
        return EvalResult(value=r, reason=f"Spearman r={r:.4f}")


class RMSE(BaseEvaluator):
    name = "rmse"
    description = "Root mean square error between predictions and references."
    required_keys = ["predictions", "references"]

    def _evaluate(self, predictions: list, references: list, **_: Any) -> EvalResult:
        x = [float(v) for v in predictions]
        y = [float(v) for v in references]
        if not x:
            return EvalResult(value=0.0, reason="Empty predictions")
        mse = sum((xi - yi) ** 2 for xi, yi in zip(x, y)) / len(x)
        rmse = math.sqrt(mse)
        return EvalResult(value=rmse, reason=f"RMSE={rmse:.4f}")


class R2Score(BaseEvaluator):
    name = "r2_score"
    description = "R-squared (coefficient of determination)."
    required_keys = ["predictions", "references"]

    def _evaluate(self, predictions: list, references: list, **_: Any) -> EvalResult:
        y_true = [float(v) for v in references]
        y_pred = [float(v) for v in predictions]
        if not y_true:
            return EvalResult(value=0.0, reason="Empty references")
        y_mean = sum(y_true) / len(y_true)
        ss_tot = sum((yi - y_mean) ** 2 for yi in y_true)
        ss_res = sum((yi - fi) ** 2 for yi, fi in zip(y_true, y_pred))
        r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 0.0
        return EvalResult(value=r2, reason=f"R2={r2:.4f}")
