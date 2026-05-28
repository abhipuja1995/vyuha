#!/usr/bin/env python3
"""
Unified local AI gateway for Vyuha.

Exposes a single port that routes:
  POST /v1/audio/transcriptions  → faster-whisper  (OpenAI Whisper API)
  POST /api/generate             → Ollama LLM      (Ollama native API)
  POST /api/chat                 → Ollama LLM
  POST /v1/chat/completions      → Ollama LLM
  GET  /api/tags                 → Ollama LLM
  GET  /health                   → this gateway

With one port, only ONE cloudflare tunnel is needed and only ONE env var
(OLLAMA_URL) must be set in Railway.

Usage:
    python local_ai_gateway.py [--port 11436] [--whisper-port 11435] [--ollama-port 11434] [--whisper-model base]

Then tunnel it:
    ./cloudflared tunnel --url http://localhost:11436 --no-autoupdate

And set in Railway:
    OLLAMA_URL = https://<tunnel-url>
    OLLAMA_LLM_URL = https://<tunnel-url>   (same URL — both go through gateway)
"""

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import threading
import time

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# ── config ────────────────────────────────────────────────────────────────────

WHISPER_PORT = int(os.environ.get("WHISPER_PORT", "11435"))
OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))
WHISPER_URL = f"http://localhost:{WHISPER_PORT}"
OLLAMA_URL = f"http://localhost:{OLLAMA_PORT}"

app = FastAPI(title="Vyuha Local AI Gateway")


@app.get("/health")
async def health():
    # Check both backends
    results: dict = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in [("whisper", WHISPER_URL), ("ollama", OLLAMA_URL)]:
            try:
                r = await client.get(f"{url}/health")
                results[name] = "ok" if r.is_success else f"http {r.status_code}"
            except Exception as exc:
                results[name] = f"unreachable: {exc}"
    return {"gateway": "ok", "backends": results}


# ── routing ───────────────────────────────────────────────────────────────────

_OLLAMA_PREFIXES = (
    "/api/",
    "/v1/chat/",
    "/v1/models",
    "/v1/completions",
    "/v1/embeddings",
)

_WHISPER_PATHS = {
    "/v1/audio/transcriptions",
    "/v1/audio/translations",
}


def _target(path: str) -> str:
    if path in _WHISPER_PATHS:
        return WHISPER_URL
    # Everything else (Ollama API, OpenAI-compat chat) goes to Ollama
    return OLLAMA_URL


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy(full_path: str, request: Request):
    target = _target("/" + full_path)
    url = f"{target}/{full_path}"
    if request.url.query:
        url += f"?{request.url.query}"

    # Forward headers, strip hop-by-hop
    HOP = {"host", "connection", "keep-alive", "transfer-encoding", "te", "upgrade"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}

    body = await request.body() or None

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            upstream = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
        except httpx.ConnectError as exc:
            svc = "Whisper server" if target == WHISPER_URL else "Ollama"
            return JSONResponse(
                {"error": f"{svc} not reachable at {target}: {exc}"},
                status_code=502,
            )

    # Build response headers (drop hop-by-hop)
    resp_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in HOP | {"content-length", "content-encoding"}
    }
    return StreamingResponse(
        content=upstream.aiter_bytes(),
        status_code=upstream.status_code,
        headers=resp_headers,
    )


# ── entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=11436)
    parser.add_argument("--whisper-port", type=int, default=11435)
    parser.add_argument("--ollama-port", type=int, default=11434)
    args = parser.parse_args()

    WHISPER_PORT = args.whisper_port
    OLLAMA_PORT = args.ollama_port
    WHISPER_URL = f"http://localhost:{WHISPER_PORT}"
    OLLAMA_URL = f"http://localhost:{OLLAMA_PORT}"

    print(f"Vyuha AI Gateway → port {args.port}")
    print(f"  /v1/audio/transcriptions → Whisper  @ {WHISPER_URL}")
    print(f"  /api/*, /v1/chat/*       → Ollama   @ {OLLAMA_URL}")
    print()
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
