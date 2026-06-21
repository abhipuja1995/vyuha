"""
LLM-as-judge evaluators — FutureAGI-parity.
Uses the Vyuha LLM router for scoring.
"""
from __future__ import annotations

from typing import Any

from vyuha.evaluators.base import BaseEvaluator, EvalResult
from vyuha.utils.llm import parse_llm_json


def _run_async(coro):
    import asyncio, concurrent.futures
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result()


class CustomPromptEvaluator(BaseEvaluator):
    name = "custom_prompt"
    description = "Evaluates output against user-defined criteria using an LLM judge."
    required_keys = ["output", "criteria"]

    def __init__(self, criteria: str = "", scale: int = 10) -> None:
        self.criteria = criteria
        self.scale = scale

    def _evaluate(self, output: str, criteria: str = "", context: str = "", **_: Any) -> EvalResult:
        from vyuha.utils.llm_router import call as llm_call
        _criteria = criteria or self.criteria
        scale = self.scale
        prompt = (
            f"Evaluate output against criteria.\n"
            f"Criteria: {_criteria}\n"
            f"Context (if any): {context}\n"
            f"Output to evaluate: {output}\n"
            f'Respond JSON: {{"score": 0-{scale}, "reason": "..."}}'
        )
        try:
            resp = _run_async(llm_call(prompt=prompt, system="You are an expert evaluator. Respond only with valid JSON.", max_tokens=512))
            data = parse_llm_json(resp.text)
            score = float(data.get("score", 0))
            reason = data.get("reason", "")
            value = score / scale
            return EvalResult(value=value, reason=reason, passed=value >= 0.7)
        except Exception as exc:
            return EvalResult(value=0.0, reason=f"LLM call failed: {exc}")


class CsatScore(BaseEvaluator):
    name = "csat_score"
    description = "Customer satisfaction score from a conversation transcript."
    required_keys = ["transcript"]

    def _evaluate(self, transcript: str, **_: Any) -> EvalResult:
        from vyuha.utils.llm_router import call as llm_call
        prompt = (
            "Rate customer satisfaction 1-10 from this conversation transcript. "
            "1=very dissatisfied, 10=very satisfied. "
            "Consider explicit satisfaction statements AND implicit cues (tone, cooperation, engagement). "
            "Only use evidence from the interaction.\n\n"
            f"Transcript:\n{transcript}\n\n"
            'Respond JSON: {"score": 1-10, "reason": "..."}'
        )
        try:
            resp = _run_async(llm_call(prompt=prompt, system="You are an expert customer experience analyst. Respond only with valid JSON.", max_tokens=512))
            data = parse_llm_json(resp.text)
            score = float(data.get("score", 5))
            reason = data.get("reason", "")
            return EvalResult(value=score / 10, reason=reason)
        except Exception as exc:
            return EvalResult(value=0.0, reason=f"LLM call failed: {exc}")


class Groundedness(BaseEvaluator):
    name = "groundedness"
    description = "Checks if output is grounded in context (no hallucination)."
    required_keys = ["output", "context"]

    def _evaluate(self, output: str, context: str, **_: Any) -> EvalResult:
        from vyuha.utils.llm_router import call as llm_call
        prompt = (
            "Is the output factually supported by the provided context? Check for hallucination.\n\n"
            f"Context: {context}\n\n"
            f"Output: {output}\n\n"
            'Respond JSON: {"grounded": true/false, "score": 0.0-1.0, "reason": "..."}'
        )
        try:
            resp = _run_async(llm_call(prompt=prompt, system="You are a fact-checking expert. Respond only with valid JSON.", max_tokens=512))
            data = parse_llm_json(resp.text)
            grounded = bool(data.get("grounded", False))
            score = float(data.get("score", 0.0))
            reason = data.get("reason", "")
            return EvalResult(value=score, passed=grounded, reason=reason)
        except Exception as exc:
            return EvalResult(value=0.0, reason=f"LLM call failed: {exc}")


class AnswerSimilarity(BaseEvaluator):
    name = "answer_similarity"
    description = "Semantic similarity between output and reference answer."
    required_keys = ["output", "expected"]

    def _evaluate(self, output: str, expected: str, **_: Any) -> EvalResult:
        from vyuha.utils.llm_router import call as llm_call
        prompt = (
            "Rate semantic similarity between the output and reference answer on 0.0-1.0 scale.\n\n"
            f"Reference: {expected}\n\n"
            f"Output: {output}\n\n"
            'Respond JSON: {"score": 0.0-1.0, "reason": "..."}'
        )
        try:
            resp = _run_async(llm_call(prompt=prompt, system="You are an expert at semantic text comparison. Respond only with valid JSON.", max_tokens=512))
            data = parse_llm_json(resp.text)
            score = float(data.get("score", 0.0))
            reason = data.get("reason", "")
            return EvalResult(value=score, reason=reason, passed=score >= 0.7)
        except Exception as exc:
            return EvalResult(value=0.0, reason=f"LLM call failed: {exc}")
