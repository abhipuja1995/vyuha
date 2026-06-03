"""
Heuristic (deterministic) evaluators — ported from FutureAGI functions.py.
No ML or LLM required. All run in <1ms.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from vyuha.evaluators.base import BaseEvaluator, EvalResult

# ── String content ────────────────────────────────────────────────────────────

class Contains(BaseEvaluator):
    name = "contains"
    description = "True if output contains the keyword."
    required_keys = ["output", "keyword"]

    def __init__(self, keyword: str = "", case_sensitive: bool = False) -> None:
        self.keyword = keyword
        self.case_sensitive = case_sensitive

    def _evaluate(self, output: str, keyword: str = "", **_: Any) -> EvalResult:
        kw = keyword or self.keyword
        text, k = (output, kw) if self.case_sensitive else (output.lower(), kw.lower())
        found = k in text
        return EvalResult(value=found, reason=f"Keyword '{kw}' {'found' if found else 'not found'} in output.")


class ContainsAny(BaseEvaluator):
    name = "contains_any"
    description = "True if output contains ANY of the keywords."
    required_keys = ["output", "keywords"]

    def __init__(self, keywords: list[str] | str = "", case_sensitive: bool = False) -> None:
        self.keywords = [keywords] if isinstance(keywords, str) else keywords
        self.case_sensitive = case_sensitive

    def _evaluate(self, output: str, keywords: list[str] | str | None = None, **_: Any) -> EvalResult:
        kws = keywords if keywords is not None else self.keywords
        if isinstance(kws, str):
            kws = [k.strip() for k in kws.split(",")]
        text = output if self.case_sensitive else output.lower()
        found = [k for k in kws if (k if self.case_sensitive else k.lower()) in text]
        ok = bool(found)
        return EvalResult(value=ok, reason=f"Found: {found}" if ok else f"None of {kws} found.")


class ContainsAll(BaseEvaluator):
    name = "contains_all"
    description = "True if output contains ALL keywords."
    required_keys = ["output", "keywords"]

    def __init__(self, keywords: list[str] | str = "", case_sensitive: bool = False) -> None:
        self.keywords = [keywords] if isinstance(keywords, str) else keywords
        self.case_sensitive = case_sensitive

    def _evaluate(self, output: str, keywords: list[str] | str | None = None, **_: Any) -> EvalResult:
        kws = keywords if keywords is not None else self.keywords
        if isinstance(kws, str):
            kws = [k.strip() for k in kws.split(",")]
        text = output if self.case_sensitive else output.lower()
        missing = [k for k in kws if (k if self.case_sensitive else k.lower()) not in text]
        ok = not missing
        return EvalResult(value=ok, reason="All found." if ok else f"Missing: {missing}")


class ContainsNone(BaseEvaluator):
    name = "contains_none"
    description = "True if output contains NONE of the keywords."
    required_keys = ["output", "keywords"]

    def __init__(self, keywords: list[str] | str = "", case_sensitive: bool = False) -> None:
        self.keywords = [keywords] if isinstance(keywords, str) else keywords
        self.case_sensitive = case_sensitive

    def _evaluate(self, output: str, keywords: list[str] | str | None = None, **_: Any) -> EvalResult:
        kws = keywords if keywords is not None else self.keywords
        if isinstance(kws, str):
            kws = [k.strip() for k in kws.split(",")]
        text = output if self.case_sensitive else output.lower()
        found = [k for k in kws if (k if self.case_sensitive else k.lower()) in text]
        ok = not found
        return EvalResult(value=ok, reason="None found." if ok else f"Forbidden words found: {found}")


class Equals(BaseEvaluator):
    name = "equals"
    description = "True if output exactly equals expected text."
    required_keys = ["output", "expected"]

    def __init__(self, expected: str = "", case_sensitive: bool = False) -> None:
        self.expected = expected
        self.case_sensitive = case_sensitive

    def _evaluate(self, output: str, expected: str = "", **_: Any) -> EvalResult:
        exp = expected or self.expected
        a, b = (output, exp) if self.case_sensitive else (output.lower().strip(), exp.lower().strip())
        ok = a == b
        return EvalResult(value=ok, reason="Exact match." if ok else f"Expected: '{exp}', got: '{output[:80]}'")


class StartsWith(BaseEvaluator):
    name = "starts_with"
    description = "True if output starts with the given prefix."
    required_keys = ["output", "prefix"]

    def __init__(self, prefix: str = "", case_sensitive: bool = False) -> None:
        self.prefix = prefix
        self.case_sensitive = case_sensitive

    def _evaluate(self, output: str, prefix: str = "", **_: Any) -> EvalResult:
        p = prefix or self.prefix
        text, pref = (output, p) if self.case_sensitive else (output.lower(), p.lower())
        ok = text.startswith(pref)
        return EvalResult(value=ok, reason=f"Output {'starts' if ok else 'does not start'} with '{p}'")


class EndsWith(BaseEvaluator):
    name = "ends_with"
    description = "True if output ends with the given suffix."
    required_keys = ["output", "suffix"]

    def __init__(self, suffix: str = "", case_sensitive: bool = False) -> None:
        self.suffix = suffix
        self.case_sensitive = case_sensitive

    def _evaluate(self, output: str, suffix: str = "", **_: Any) -> EvalResult:
        s = suffix or self.suffix
        text, suf = (output, s) if self.case_sensitive else (output.lower(), s.lower())
        ok = text.endswith(suf)
        return EvalResult(value=ok, reason=f"Output {'ends' if ok else 'does not end'} with '{s}'")


class Regex(BaseEvaluator):
    name = "regex"
    description = "True if output matches the regex pattern."
    required_keys = ["output", "pattern"]

    def __init__(self, pattern: str = "") -> None:
        self.pattern = pattern

    def _evaluate(self, output: str, pattern: str = "", **_: Any) -> EvalResult:
        p = pattern or self.pattern
        match = re.search(p, output)
        ok = bool(match)
        return EvalResult(value=ok, reason=f"Pattern '{p}' {'matched' if ok else 'did not match'}")


# ── Length / count ────────────────────────────────────────────────────────────

class LengthLessThan(BaseEvaluator):
    name = "length_less_than"
    description = "True if len(output) < max_length."
    required_keys = ["output"]

    def __init__(self, max_length: int = 500) -> None:
        self.max_length = max_length

    def _evaluate(self, output: str, max_length: int | None = None, **_: Any) -> EvalResult:
        ml = max_length if max_length is not None else self.max_length
        ln = len(output)
        ok = ln < ml
        return EvalResult(value=ok, reason=f"Length {ln} {'<' if ok else '>='} {ml}")


class LengthGreaterThan(BaseEvaluator):
    name = "length_greater_than"
    description = "True if len(output) > min_length."
    required_keys = ["output"]

    def __init__(self, min_length: int = 0) -> None:
        self.min_length = min_length

    def _evaluate(self, output: str, min_length: int | None = None, **_: Any) -> EvalResult:
        ml = min_length if min_length is not None else self.min_length
        ln = len(output)
        ok = ln > ml
        return EvalResult(value=ok, reason=f"Length {ln} {'>' if ok else '<='} {ml}")


class LengthBetween(BaseEvaluator):
    name = "length_between"
    description = "True if min_length <= len(output) <= max_length."
    required_keys = ["output"]

    def __init__(self, min_length: int = 0, max_length: int = 1000) -> None:
        self.min_length = min_length
        self.max_length = max_length

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        ln = len(output)
        ok = self.min_length <= ln <= self.max_length
        return EvalResult(value=ok, reason=f"Length {ln} {'in' if ok else 'out of'} [{self.min_length}, {self.max_length}]")


class WordCountInRange(BaseEvaluator):
    name = "word_count_in_range"
    description = "True if word count is within [min_words, max_words]."
    required_keys = ["output"]

    def __init__(self, min_words: int = 0, max_words: int = 500) -> None:
        self.min_words = min_words
        self.max_words = max_words

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        wc = len(output.split())
        ok = self.min_words <= wc <= self.max_words
        return EvalResult(value=ok, reason=f"Word count {wc} {'in' if ok else 'out of'} [{self.min_words}, {self.max_words}]")


class OneLine(BaseEvaluator):
    name = "one_line"
    description = "True if output has no newlines."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        ok = "\n" not in output.strip()
        return EvalResult(value=ok, reason="Single line." if ok else "Multiple lines detected.")


# ── Format validation ─────────────────────────────────────────────────────────

class IsJson(BaseEvaluator):
    name = "is_json"
    description = "True if output is valid JSON."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        try:
            json.loads(output)
            return EvalResult(value=True, reason="Valid JSON.")
        except (json.JSONDecodeError, ValueError) as exc:
            return EvalResult(value=False, reason=f"Invalid JSON: {exc}")


class IsUrl(BaseEvaluator):
    name = "is_url"
    description = "True if output is a valid URL."
    required_keys = ["output"]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        try:
            parsed = urllib.parse.urlparse(output.strip())
            ok = parsed.scheme in ("http", "https") and bool(parsed.netloc)
            return EvalResult(value=ok, reason="Valid URL." if ok else "Not a valid URL.")
        except Exception:
            return EvalResult(value=False, reason="URL parse error.")


class IsEmail(BaseEvaluator):
    name = "is_email"
    description = "True if output is a valid email address."
    required_keys = ["output"]

    _EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        ok = bool(self._EMAIL_RE.match(output.strip()))
        return EvalResult(value=ok, reason="Valid email." if ok else "Not a valid email.")


class IsRefusal(BaseEvaluator):
    name = "is_refusal"
    description = "True if the agent response is a refusal (cannot/won't help)."
    required_keys = ["output"]

    _REFUSAL_PATTERNS = [
        r"\bI (can't|cannot|won't|am unable to|am not able to)\b",
        r"\b(sorry|apologies|apologize)\b.*\b(cannot|can't|won't|unable)\b",
        r"\bI don't have (the ability|permission|access)\b",
        r"\bthat('s| is) (outside|beyond) (my|the)\b",
        r"\bI (must|need to) (decline|refuse)\b",
        r"\bThis (request|query) (cannot|can't) be\b",
    ]
    _COMPILED = [re.compile(p, re.IGNORECASE) for p in _REFUSAL_PATTERNS]

    def _evaluate(self, output: str, **_: Any) -> EvalResult:
        for pattern in self._COMPILED:
            if pattern.search(output):
                return EvalResult(value=True, reason="Refusal pattern detected.")
        return EvalResult(value=False, reason="No refusal pattern detected.")
