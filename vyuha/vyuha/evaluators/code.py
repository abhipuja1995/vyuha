"""
Code / text quality evaluators — FutureAGI-parity.
No LLM required. All deterministic.
"""
from __future__ import annotations

import json
import re
import string
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any

from vyuha.evaluators.base import BaseEvaluator, EvalResult


class SyntaxValidation(BaseEvaluator):
    name = "syntax_validation"
    description = "Validates code syntax (Python supported)."
    required_keys = ["output"]

    def _evaluate(self, output: str, language: str = "python", **_: Any) -> EvalResult:
        if language == "python":
            import ast
            try:
                ast.parse(output)
                return EvalResult(value=True, reason="Valid Python syntax.", passed=True)
            except SyntaxError as exc:
                return EvalResult(value=False, reason=f"SyntaxError: {exc}", passed=False)
        return EvalResult(value=True, reason=f"No syntax check available for {language}.", passed=True)


def _count_syllables(word: str) -> int:
    word = word.lower()
    vowels = "aeiou"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # silent e
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


class ReadabilityScore(BaseEvaluator):
    name = "readability_score"
    description = "Flesch Reading Ease score (0-1 normalized)."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        sentences = [s.strip() for s in re.split(r'[.!?]+', output) if s.strip()]
        words = output.split()
        if not sentences or not words:
            return EvalResult(value=0.0, reason="Insufficient text.")
        num_syllables = sum(_count_syllables(w) for w in words)
        score = (
            206.835
            - 1.015 * (len(words) / len(sentences))
            - 84.6 * (num_syllables / len(words))
        )
        score = max(0.0, min(100.0, score))
        return EvalResult(value=score / 100.0, reason=f"Flesch {score:.1f}/100")


class DistinctN(BaseEvaluator):
    name = "distinct_n"
    description = "Ratio of distinct n-grams to total n-grams."
    required_keys = ["output"]

    def __init__(self, n: int = 2) -> None:
        self.n = n

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        tokens = output.split()
        if len(tokens) < self.n:
            return EvalResult(value=0.0, reason="Text too short for n-grams.")
        ngrams = [tuple(tokens[i:i + self.n]) for i in range(len(tokens) - self.n + 1)]
        if not ngrams:
            return EvalResult(value=0.0, reason="No n-grams found.")
        ratio = len(set(ngrams)) / len(ngrams)
        return EvalResult(value=ratio, reason=f"Distinct-{self.n}={ratio:.3f}")


class TypeTokenRatio(BaseEvaluator):
    name = "type_token_ratio"
    description = "Ratio of unique words to total words (lexical diversity)."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        words = output.lower().split()
        if not words:
            return EvalResult(value=0.0, reason="Empty output.")
        ratio = len(set(words)) / len(words)
        return EvalResult(value=ratio, reason=f"TTR={ratio:.3f}")


class RepetitionRate(BaseEvaluator):
    name = "repetition_rate"
    description = "Fraction of repeated sentences in output."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        sentences = [s.strip().lower() for s in re.split(r'[.!?]+', output) if s.strip()]
        if not sentences:
            return EvalResult(value=0.0, reason="No sentences found.", passed=True)
        counts = Counter(sentences)
        duplicates = sum(v - 1 for v in counts.values())
        rate = duplicates / len(sentences)
        return EvalResult(value=rate, reason=f"RepetitionRate={rate:.3f}", passed=rate < 0.2)


def _normalize_squad(text: str) -> list[str]:
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return text.split()


class SquadScore(BaseEvaluator):
    name = "squad_score"
    description = "SQuAD-style exact match + token F1 score."
    required_keys = ["output", "expected"]

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        out_tokens = _normalize_squad(output)
        ref_tokens = _normalize_squad(expected)
        exact_match = 1 if out_tokens == ref_tokens else 0
        common = sum(
            min(Counter(out_tokens)[t], Counter(ref_tokens)[t])
            for t in set(out_tokens) & set(ref_tokens)
        )
        denom = len(out_tokens) + len(ref_tokens)
        token_f1 = 2 * common / denom if denom > 0 else 0.0
        value = (exact_match + token_f1) / 2
        return EvalResult(value=value, reason=f"EM={exact_match}, F1={token_f1:.3f}")


class ContainsJson(BaseEvaluator):
    name = "contains_json"
    description = "True if output contains parseable JSON."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        idx = output.find("{")
        if idx == -1:
            idx = output.find("[")
        if idx == -1:
            return EvalResult(value=False, reason="No JSON found.", passed=False)
        try:
            json.loads(output[idx:])
            return EvalResult(value=True, reason="Valid JSON found.", passed=True)
        except Exception:
            return EvalResult(value=False, reason="JSON parse failed.", passed=False)


class ContainsEmail(BaseEvaluator):
    name = "contains_email"
    description = "True if output contains an email address."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        found = bool(re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', output))
        return EvalResult(value=found, reason="Email found." if found else "No email found.", passed=found)


class ContainsLink(BaseEvaluator):
    name = "contains_link"
    description = "True if output contains an HTTP/HTTPS URL."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        found = bool(re.search(r'https?://[^\s]+', output))
        return EvalResult(value=found, reason="URL found." if found else "No URL found.", passed=found)


class IsXml(BaseEvaluator):
    name = "is_xml"
    description = "True if output is valid XML."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        try:
            ET.fromstring(output.strip())
            return EvalResult(value=True, reason="Valid XML.", passed=True)
        except Exception as exc:
            return EvalResult(value=False, reason=f"Invalid XML: {exc}", passed=False)


class IsHtml(BaseEvaluator):
    name = "is_html"
    description = "True if output contains HTML tags."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        found = bool(re.search(r'<(html|body|div|p|span|h[1-6]|table|head)[^>]*>', output, re.IGNORECASE))
        return EvalResult(value=found, reason="HTML tags found." if found else "No HTML tags.", passed=found)


class IsSql(BaseEvaluator):
    name = "is_sql"
    description = "True if output starts with a SQL keyword."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        keywords = ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "WITH")
        found = output.strip().upper().startswith(keywords)
        return EvalResult(value=found, reason="SQL statement detected." if found else "Not SQL.", passed=found)


class JsonSchema(BaseEvaluator):
    name = "json_schema"
    description = "Validates output JSON against a JSON schema."
    required_keys = ["output", "schema"]

    def _evaluate(self, output: str, schema: dict, **_: Any) -> EvalResult:
        try:
            instance = json.loads(output)
        except Exception as exc:
            return EvalResult(value=False, reason=f"JSON parse failed: {exc}", passed=False)
        try:
            import jsonschema
            jsonschema.validate(instance=instance, schema=schema)
            return EvalResult(value=True, reason="Schema validation passed.", passed=True)
        except ImportError:
            return EvalResult(value=True, reason="jsonschema not installed; skipped.", passed=True)
        except Exception as exc:
            return EvalResult(value=False, reason=f"Schema validation failed: {exc}", passed=False)


class SentenceCount(BaseEvaluator):
    name = "sentence_count"
    description = "Checks sentence count is within min/max bounds."
    required_keys = ["output"]

    def __init__(self, min_sentences: int = 1, max_sentences: int = 100) -> None:
        self.min_sentences = min_sentences
        self.max_sentences = max_sentences

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        sentences = [s.strip() for s in re.split(r'[.!?]+', output) if s.strip()]
        count = len(sentences)
        passed = self.min_sentences <= count <= self.max_sentences
        return EvalResult(
            value=count / self.max_sentences,
            reason=f"Sentence count={count} (min={self.min_sentences}, max={self.max_sentences})",
            passed=passed,
        )
