from __future__ import annotations

import json
from enum import Enum
from typing import Any

import anthropic
import structlog
from openai import AsyncOpenAI

from vyuha.config import settings

log = structlog.get_logger()


class JudgeModel(str, Enum):
    CLAUDE_SONNET = "claude-sonnet-4-6"
    GPT4O = "gpt-4o"


# Per-metric model configuration — override in judge_config.json
_DEFAULT_JUDGE_CONFIG: dict[str, str] = {
    "faithfulness": JudgeModel.CLAUDE_SONNET,
    "conciseness": JudgeModel.CLAUDE_SONNET,
    "conversation_progression": JudgeModel.CLAUDE_SONNET,
    "turn_taking": JudgeModel.CLAUDE_SONNET,
    "rca_tagging": JudgeModel.CLAUDE_SONNET,
    "speech_fidelity": JudgeModel.CLAUDE_SONNET,
}


def _load_judge_config() -> dict[str, str]:
    import pathlib
    config_path = pathlib.Path("judge_config.json")
    if config_path.exists():
        with open(config_path) as f:
            return {**_DEFAULT_JUDGE_CONFIG, **json.load(f)}
    return _DEFAULT_JUDGE_CONFIG


_JUDGE_CONFIG = _load_judge_config()


class LLMJudge:
    """
    Configurable LLM judge. Uses Claude Sonnet 4.6 by default,
    falls back to GPT-4o, configurable per metric via judge_config.json.
    Clients are lazily initialized so tests without API keys don't fail at import.
    """

    def __init__(self) -> None:
        self._anthropic_client: anthropic.AsyncAnthropic | None = None
        self._openai_client: AsyncOpenAI | None = None

    @property
    def _anthropic(self) -> anthropic.AsyncAnthropic:
        if self._anthropic_client is None:
            self._anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._anthropic_client

    @property
    def _openai(self) -> AsyncOpenAI:
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key or "placeholder")
        return self._openai_client

    async def judge(
        self,
        metric: str,
        prompt: str,
        context: dict[str, Any],
        system: str = "",
    ) -> dict[str, Any]:
        """Route to best available LLM automatically."""
        from vyuha.utils import llm_router
        full_prompt = f"{prompt}\n\nContext:\n{json.dumps(context, indent=2)}"
        try:
            resp = await llm_router.call(full_prompt, system=system or "You are a precise evaluator. Always respond with valid JSON.")
            log.debug("judge_used", metric=metric, provider=resp.provider, model=resp.model)
            from vyuha.utils.llm import parse_llm_json
            try:
                return parse_llm_json(resp.text)
            except json.JSONDecodeError:
                log.error("judge_json_parse_failed", provider=resp.provider, raw=resp.text[:200])
                return {"score": 0.0, "reason": "Parse error", "raw": resp.text}
        except Exception as exc:
            log.error("judge_all_llm_failed", metric=metric, error=str(exc))
            return {"score": 0.0, "reason": f"LLM unavailable: {exc}"}

    async def _call_model(
        self, model: str, prompt: str, context: dict[str, Any], system: str
    ) -> dict[str, Any]:
        full_prompt = f"{prompt}\n\nContext:\n{json.dumps(context, indent=2)}"

        if "claude" in model:
            response = await self._anthropic.messages.create(
                model=model,
                max_tokens=1024,
                system=system or "You are a precise evaluator. Always respond with valid JSON.",
                messages=[{"role": "user", "content": full_prompt}],
            )
            raw = response.content[0].text
        else:
            response = await self._openai.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system or "You are a precise evaluator. Always respond with valid JSON."},
                    {"role": "user", "content": full_prompt},
                ],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"

        try:
            from vyuha.utils.llm import parse_llm_json
            return parse_llm_json(raw)
        except json.JSONDecodeError:
            log.error("judge_json_parse_failed", model=model, raw=raw[:200])
            return {"score": 0.0, "reason": "Parse error", "raw": raw}
