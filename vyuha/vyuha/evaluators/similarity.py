"""
Text similarity evaluators — ported from FutureAGI functions.py.
Requires: rouge-score, nltk, rapidfuzz (lightweight; no PyTorch needed for most).
EmbeddingSimilarity lazily loads sentence-transformers on first use.
"""
from __future__ import annotations

from typing import Any

from vyuha.evaluators.base import BaseEvaluator, EvalResult


class RougeScore(BaseEvaluator):
    name = "rouge_score"
    description = "ROUGE-1/2/L F-measure between output and expected."
    required_keys = ["output", "expected"]

    def __init__(self, rouge_type: str = "rouge1", pass_threshold: float | None = None) -> None:
        self.rouge_type = rouge_type
        self.pass_threshold = pass_threshold

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        try:
            from rouge_score import rouge_scorer
            scorer = rouge_scorer.RougeScorer([self.rouge_type], use_stemmer=True)
            scores = scorer.score(expected, output)
            score = round(scores[self.rouge_type].fmeasure, 4)
            return EvalResult(value=score, reason=f"{self.rouge_type.upper()} F-measure: {score}")
        except ImportError:
            return EvalResult(value=0.0, reason="rouge-score not installed. pip install rouge-score")


class BleuScore(BaseEvaluator):
    name = "bleu_score"
    description = "BLEU score between output (hypothesis) and expected (reference)."
    required_keys = ["output", "expected"]

    def __init__(self, pass_threshold: float | None = None) -> None:
        self.pass_threshold = pass_threshold

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        try:
            from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
            ref = expected.split()
            hyp = output.split()
            score = round(sentence_bleu([ref], hyp, smoothing_function=SmoothingFunction().method4), 4)
            return EvalResult(value=score, reason=f"BLEU score: {score}")
        except ImportError:
            return EvalResult(value=0.0, reason="nltk not installed. pip install nltk")


class MeteorScore(BaseEvaluator):
    name = "meteor_score"
    description = "METEOR score (harmonic mean of precision and recall with chunking penalty)."
    required_keys = ["output", "expected"]

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        try:
            from nltk.translate.meteor_score import meteor_score
            score = round(meteor_score([expected.split()], output.split()), 4)
            return EvalResult(value=score, reason=f"METEOR score: {score}")
        except ImportError:
            return EvalResult(value=0.0, reason="nltk not installed. pip install nltk")


class F1Score(BaseEvaluator):
    name = "f1_score"
    description = "Token-level F1 between output and expected (common in QA evaluation)."
    required_keys = ["output", "expected"]

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        pred_tokens = set(output.lower().split())
        ref_tokens = set(expected.lower().split())
        if not pred_tokens or not ref_tokens:
            score = 1.0 if pred_tokens == ref_tokens else 0.0
            return EvalResult(value=score, reason=f"F1: {score} (empty tokens)")
        common = pred_tokens & ref_tokens
        if not common:
            return EvalResult(value=0.0, reason="No common tokens.")
        precision = len(common) / len(pred_tokens)
        recall = len(common) / len(ref_tokens)
        f1 = round(2 * precision * recall / (precision + recall), 4)
        return EvalResult(value=f1, reason=f"F1: {f1} (P={precision:.2f}, R={recall:.2f})")


class LevenshteinSimilarity(BaseEvaluator):
    name = "levenshtein_similarity"
    description = "Normalised Levenshtein similarity (1 - distance/max_len)."
    required_keys = ["output", "expected"]

    def __init__(self, case_insensitive: bool = True, pass_threshold: float | None = None) -> None:
        self.case_insensitive = case_insensitive
        self.pass_threshold = pass_threshold

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        try:
            from rapidfuzz.distance import Levenshtein
            a, b = (output.lower(), expected.lower()) if self.case_insensitive else (output, expected)
            distance = Levenshtein.distance(a, b)
            max_len = max(len(a), len(b), 1)
            score = round(1.0 - distance / max_len, 4)
            return EvalResult(value=score, reason=f"Levenshtein similarity: {score} (distance={distance})")
        except ImportError:
            # Pure Python fallback
            a, b = (output.lower(), expected.lower()) if self.case_insensitive else (output, expected)
            m, n = len(a), len(b)
            dp = list(range(n + 1))
            for i in range(1, m + 1):
                prev = dp[:]
                dp[0] = i
                for j in range(1, n + 1):
                    dp[j] = prev[j - 1] if a[i - 1] == b[j - 1] else 1 + min(prev[j], dp[j - 1], prev[j - 1])
            score = round(1.0 - dp[n] / max(m, n, 1), 4)
            return EvalResult(value=score, reason=f"Levenshtein similarity: {score}")


class JaccardSimilarity(BaseEvaluator):
    name = "jaccard_similarity"
    description = "Jaccard similarity on word sets: |intersection| / |union|."
    required_keys = ["output", "expected"]

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        a = set(output.lower().split())
        b = set(expected.lower().split())
        union = a | b
        if not union:
            return EvalResult(value=1.0, reason="Both empty — identical.")
        score = round(len(a & b) / len(union), 4)
        return EvalResult(value=score, reason=f"Jaccard: {score}")


class JaroWinklerSimilarity(BaseEvaluator):
    name = "jaro_winkler_similarity"
    description = "Jaro-Winkler string similarity."
    required_keys = ["output", "expected"]

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        try:
            from rapidfuzz.distance import JaroWinkler
            score = round(JaroWinkler.similarity(output, expected), 4)
        except ImportError:
            # minimal Jaro
            s1, s2 = output, expected
            if s1 == s2:
                return EvalResult(value=1.0, reason="Exact match.")
            match_dist = max(len(s1), len(s2)) // 2 - 1
            s1m = [False] * len(s1); s2m = [False] * len(s2)
            matches = 0
            for i, c in enumerate(s1):
                lo, hi = max(0, i - match_dist), min(i + match_dist + 1, len(s2))
                for j in range(lo, hi):
                    if not s2m[j] and c == s2[j]:
                        s1m[i] = s2m[j] = True; matches += 1; break
            if not matches:
                return EvalResult(value=0.0, reason="No matches.")
            t = sum(c1 != c2 for c1, c2 in zip(
                (c for c, m in zip(s1, s1m) if m),
                (c for c, m in zip(s2, s2m) if m),
            )) / 2
            jaro = (matches / len(s1) + matches / len(s2) + (matches - t) / matches) / 3
            prefix = sum(1 for a, b in zip(s1[:4], s2[:4]) if a == b)
            score = round(jaro + prefix * 0.1 * (1 - jaro), 4)
        return EvalResult(value=score, reason=f"Jaro-Winkler: {score}")


class FuzzyMatch(BaseEvaluator):
    name = "fuzzy_match"
    description = "RapidFuzz partial ratio similarity (0-1)."
    required_keys = ["output", "expected"]

    def __init__(self, pass_threshold: float | None = 0.8) -> None:
        self.pass_threshold = pass_threshold

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        try:
            from rapidfuzz import fuzz
            score = round(fuzz.partial_ratio(output, expected) / 100.0, 4)
        except ImportError:
            # fall back to Jaccard
            a, b = set(output.lower().split()), set(expected.lower().split())
            score = round(len(a & b) / max(len(a | b), 1), 4)
        return EvalResult(value=score, reason=f"Fuzzy match ratio: {score}")


class EmbeddingSimilarity(BaseEvaluator):
    """
    Cosine similarity between sentence-transformer embeddings.
    Lazily loads 'all-MiniLM-L6-v2' on first call (~80MB, cached).
    Falls back to Jaccard if sentence-transformers is unavailable.
    """
    name = "embedding_similarity"
    description = "Cosine similarity between semantic embeddings of output and expected."
    required_keys = ["output", "expected"]

    _model = None

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        pass_threshold: float | None = 0.7,
    ) -> None:
        self.model_name = model_name
        self.pass_threshold = pass_threshold

    @classmethod
    def _get_model(cls, model_name: str):
        if cls._model is None:
            from sentence_transformers import SentenceTransformer
            cls._model = SentenceTransformer(model_name)
        return cls._model

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        try:
            from scipy.spatial.distance import cosine
            model = self._get_model(self.model_name)
            emb1 = model.encode([output])[0]
            emb2 = model.encode([expected])[0]
            score = round(float(1.0 - cosine(emb1, emb2)), 4)
            return EvalResult(value=score, reason=f"Embedding cosine similarity: {score}")
        except ImportError:
            # Jaccard fallback
            a = set(output.lower().split())
            b = set(expected.lower().split())
            score = round(len(a & b) / max(len(a | b), 1), 4)
            return EvalResult(value=score, reason=f"Jaccard fallback similarity: {score} (install sentence-transformers for embeddings)")
