"""
LLM auto-router — picks the best available LLM based on configured API keys.

Priority: Claude (Anthropic) → GPT-4o (OpenAI) → local Ollama → error

No user selection per task. The system always uses the best active LLM.
Callers get back a unified `LLMResponse` and a `provider_used` label for UI display.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from vyuha.config import settings
from vyuha.utils.llm import parse_llm_json

log = structlog.get_logger()


@dataclass
class LLMResponse:
    text: str
    provider: str          # "claude-sonnet-4-6", "gpt-4o", "ollama/llama3.2"
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


async def _call_anthropic(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
) -> LLMResponse:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    model = settings.default_judge_model
    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "Respond with valid JSON only.",
        messages=[{"role": "user", "content": prompt}],
    )
    return LLMResponse(
        text=resp.content[0].text,
        provider="anthropic",
        model=model,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
    )


async def _call_openai(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
) -> LLMResponse:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    model = settings.fallback_judge_model
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system or "Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    )
    return LLMResponse(
        text=resp.choices[0].message.content or "",
        provider="openai",
        model=model,
        input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
        output_tokens=resp.usage.completion_tokens if resp.usage else 0,
    )


async def _call_ollama(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
) -> LLMResponse:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key="ollama", base_url=settings.local_llm_url)
    model = settings.local_llm_model
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system or "Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    )
    return LLMResponse(
        text=resp.choices[0].message.content or "",
        provider="ollama",
        model=model,
    )


def active_provider() -> str:
    """Return label of the best currently-configured LLM provider. Ollama first."""
    if settings.local_llm_url:
        return f"ollama/{settings.local_llm_model}"
    if settings.anthropic_api_key:
        return f"claude/{settings.default_judge_model}"
    if settings.openai_api_key:
        return f"openai/{settings.fallback_judge_model}"
    return "none"


async def call(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
) -> LLMResponse:
    """
    Call the best available LLM. Priority: Ollama (local) → Anthropic → OpenAI.
    Local Ollama is preferred — cloud keys are fallback.
    Raises RuntimeError if nothing is configured.
    """
    if settings.local_llm_url:
        try:
            resp = await _call_ollama(prompt, system, max_tokens)
            log.debug("llm_router_used", provider="ollama", model=resp.model)
            return resp
        except Exception as exc:
            log.warning("llm_router_ollama_failed", error=str(exc))

    if settings.anthropic_api_key:
        try:
            resp = await _call_anthropic(prompt, system, max_tokens)
            log.debug("llm_router_used", provider="anthropic", model=resp.model)
            return resp
        except Exception as exc:
            log.warning("llm_router_anthropic_failed", error=str(exc))

    if settings.openai_api_key:
        try:
            resp = await _call_openai(prompt, system, max_tokens)
            log.debug("llm_router_used", provider="openai", model=resp.model)
            return resp
        except Exception as exc:
            log.warning("llm_router_openai_failed", error=str(exc))

    raise RuntimeError(
        "No LLM configured. Set LOCAL_LLM_URL, ANTHROPIC_API_KEY, or OPENAI_API_KEY in .env."
    )


async def call_json(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
) -> tuple[dict[str, Any], str]:
    """
    Call LLM and parse JSON response.
    Returns (parsed_dict, provider_label).
    """
    resp = await call(prompt, system, max_tokens)
    data = parse_llm_json(resp.text)
    return data, resp.provider
