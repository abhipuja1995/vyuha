"""
/settings/providers — Live provider status and runtime configuration.

Exposes:
  GET  /settings/providers          → current provider config + reachability
  POST /settings/providers          → update runtime provider config
  GET  /settings/providers/test/llm → test LLM judge connection
  GET  /settings/providers/test/stt → test STT (Ollama Whisper) connection
  GET  /settings/providers/test/tts → test TTS connection
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from vyuha.config import settings

log = structlog.get_logger()
router = APIRouter()


# ── Status helpers ────────────────────────────────────────────────────────────

async def _ping(url: str, timeout: float = 3.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
            return r.is_success or r.status_code < 500
    except Exception:
        return False


async def _ollama_models(base_url: str) -> list[str]:
    """Return list of model names available on an Ollama instance."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base_url.rstrip('/')}/api/tags")
        if r.is_success:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


async def _test_anthropic() -> dict[str, Any]:
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        # Minimal call to verify the key
        await client.messages.create(
            model=settings.default_judge_model,
            max_tokens=5,
            messages=[{"role": "user", "content": "hi"}],
        )
        return {"ok": True, "model": settings.default_judge_model}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


async def _test_openai() -> dict[str, Any]:
    if not settings.openai_api_key:
        return {"ok": False, "error": "OPENAI_API_KEY not set"}
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        await client.chat.completions.create(
            model=settings.fallback_judge_model,
            max_tokens=5,
            messages=[{"role": "user", "content": "hi"}],
        )
        return {"ok": True, "model": settings.fallback_judge_model}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


async def _test_local_llm() -> dict[str, Any]:
    if not settings.local_llm_url:
        return {"ok": False, "configured": False}
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key="ollama", base_url=settings.local_llm_url)
        await client.chat.completions.create(
            model=settings.local_llm_model,
            max_tokens=5,
            messages=[{"role": "user", "content": "hi"}],
        )
        models = await _ollama_models(settings.local_llm_url.replace("/v1", ""))
        return {"ok": True, "model": settings.local_llm_model, "available_models": models}
    except Exception as exc:
        return {"ok": False, "configured": True, "error": str(exc)[:120]}


async def _test_ollama_stt() -> dict[str, Any]:
    if not settings.ollama_url:
        return {"ok": False, "configured": False}
    base = settings.ollama_url.rstrip("/")

    # Try /health first (local_whisper_server), then /api/tags (native Ollama)
    health_ok = await _ping(f"{base}/health")
    if health_ok:
        return {
            "ok": True,
            "configured": True,
            "url": base,
            "model": settings.ollama_stt_model,
            "server": "local_whisper_server",
            "available_models": [settings.ollama_stt_model],
            "whisper_available": True,
        }

    # Fallback: check if it's a native Ollama with whisper
    models = await _ollama_models(base)
    has_whisper = any("whisper" in m.lower() for m in models)
    if not models and not has_whisper:
        return {"ok": False, "configured": True, "error": f"Cannot reach {base}", "url": base}
    return {
        "ok": has_whisper,
        "configured": True,
        "url": base,
        "model": settings.ollama_stt_model,
        "server": "ollama",
        "available_models": models,
        "whisper_available": has_whisper,
    }


async def _test_local_tts() -> dict[str, Any]:
    if not settings.local_tts_url:
        return {"ok": False, "configured": False}
    from vyuha.tts.local import LocalTTSProvider
    result = await LocalTTSProvider().health_check()
    return result


async def _test_sarvam() -> dict[str, Any]:
    if not settings.sarvam_api_key:
        return {"ok": False, "configured": False}
    try:
        async with httpx.AsyncClient(
            base_url="https://api.sarvam.ai",
            headers={"API-Subscription-Key": settings.sarvam_api_key},
            timeout=5.0,
        ) as client:
            r = await client.get("/text-to-speech/voices?language=hi-IN")
        return {"ok": r.is_success, "configured": True}
    except Exception as exc:
        return {"ok": False, "configured": True, "error": str(exc)[:80]}


async def _test_azure_tts() -> dict[str, Any]:
    if not settings.azure_speech_key:
        return {"ok": False, "configured": False}
    return {
        "ok": True,   # We only check key presence — actual test requires azure SDK import
        "configured": True,
        "region": settings.azure_speech_region,
        "note": "Key present — full test requires audio synthesis",
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def get_provider_status() -> dict[str, Any]:
    """Return current config and live reachability for all providers."""
    llm_status, stt_status, local_tts_status, sarvam_status, azure_status = await asyncio.gather(
        _test_local_llm(),
        _test_ollama_stt(),
        _test_local_tts(),
        _test_sarvam(),
        _test_azure_tts(),
    )

    return {
        "llm": {
            "primary": {
                "provider": "anthropic",
                "model": settings.default_judge_model,
                "configured": bool(settings.anthropic_api_key),
                "api_key_set": bool(settings.anthropic_api_key),
            },
            "fallback": {
                "provider": "openai",
                "model": settings.fallback_judge_model,
                "configured": bool(settings.openai_api_key),
                "api_key_set": bool(settings.openai_api_key),
            },
            "local": {
                "provider": "ollama",
                "url": settings.local_llm_url or None,
                "model": settings.local_llm_model,
                "configured": bool(settings.local_llm_url),
                **llm_status,
            },
        },
        "stt": {
            "ollama_whisper": {
                "provider": "ollama",
                "url": settings.ollama_url or None,
                "model": settings.ollama_stt_model,
                "llm_url": settings.ollama_llm_url or None,
                "llm_model": settings.ollama_llm_model,
                **stt_status,
            },
        },
        "tts": {
            "local": {
                "provider": "local",
                "url": settings.local_tts_url or None,
                "model": settings.local_tts_model,
                "voice": settings.local_tts_voice,
                **local_tts_status,
            },
            "sarvam": {
                "provider": "sarvam",
                **sarvam_status,
            },
            "azure": {
                "provider": "azure",
                **azure_status,
            },
        },
        "active_providers": {
            "llm_judge": "local" if (settings.local_llm_url and llm_status.get("ok")) else "anthropic",
            "stt": "ollama" if (settings.ollama_url and stt_status.get("ok")) else "none",
            "tts": (
                "local" if (settings.local_tts_url and local_tts_status.get("reachable"))
                else "sarvam" if settings.sarvam_api_key
                else "azure" if settings.azure_speech_key
                else "none"
            ),
        },
    }


class ProviderConfig(BaseModel):
    """Runtime provider config override (restarts factory, survives until pod restart)."""
    local_llm_url: str | None = None
    local_llm_model: str | None = None
    local_tts_url: str | None = None
    local_tts_voice: str | None = None
    ollama_url: str | None = None
    ollama_stt_model: str | None = None
    ollama_llm_url: str | None = None
    ollama_llm_model: str | None = None


@router.post("")
async def update_provider_config(config: ProviderConfig) -> dict[str, Any]:
    """
    Override provider URLs at runtime (takes effect immediately, no restart needed).
    Values are applied to the settings singleton for this process lifetime.
    To persist across restarts, set the corresponding env vars in .env.
    """
    changed = {}
    if config.local_llm_url is not None:
        settings.local_llm_url = config.local_llm_url
        changed["local_llm_url"] = config.local_llm_url
    if config.local_llm_model is not None:
        settings.local_llm_model = config.local_llm_model
        changed["local_llm_model"] = config.local_llm_model
    if config.local_tts_url is not None:
        settings.local_tts_url = config.local_tts_url
        changed["local_tts_url"] = config.local_tts_url
        # Rebuild TTS factory with new local URL
        from vyuha.tts.factory import tts_factory
        from vyuha.tts.local import LocalTTSProvider
        tts_factory._local = LocalTTSProvider()
        tts_factory._providers = [tts_factory._local, tts_factory._sarvam, tts_factory._azure]
    if config.local_tts_voice is not None:
        settings.local_tts_voice = config.local_tts_voice
        changed["local_tts_voice"] = config.local_tts_voice
    if config.ollama_url is not None:
        settings.ollama_url = config.ollama_url
        changed["ollama_url"] = config.ollama_url
    if config.ollama_stt_model is not None:
        settings.ollama_stt_model = config.ollama_stt_model
        changed["ollama_stt_model"] = config.ollama_stt_model
    if config.ollama_llm_url is not None:
        settings.ollama_llm_url = config.ollama_llm_url
        changed["ollama_llm_url"] = config.ollama_llm_url
    if config.ollama_llm_model is not None:
        settings.ollama_llm_model = config.ollama_llm_model
        changed["ollama_llm_model"] = config.ollama_llm_model

    log.info("provider_config_updated", changed=list(changed.keys()))
    return {"updated": changed, "message": "Config applied. Set env vars in .env to persist across restarts."}


@router.get("/test/llm")
async def test_llm() -> dict[str, Any]:
    """Live test: try a minimal completion against each configured LLM."""
    local, anthropic_r, openai_r = await asyncio.gather(
        _test_local_llm(),
        _test_anthropic(),
        _test_openai(),
    )
    return {"local": local, "anthropic": anthropic_r, "openai": openai_r}


@router.get("/test/stt")
async def test_stt() -> dict[str, Any]:
    """Live test: ping Ollama and list available models."""
    return await _test_ollama_stt()


@router.get("/test/tts")
async def test_tts() -> dict[str, Any]:
    """Live test: ping each TTS provider."""
    local, sarvam, azure = await asyncio.gather(
        _test_local_tts(),
        _test_sarvam(),
        _test_azure_tts(),
    )
    return {"local": local, "sarvam": sarvam, "azure": azure}
