from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vyuha.config import settings
from vyuha.orchestrator.routes import test_cases, runs, reports, generate, ingest, audio

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("vyuha_api_starting")
    yield
    log.info("vyuha_api_shutdown")


app = FastAPI(
    title="Vyuha API",
    description="Voice AI Evaluation System — Bot-to-Bot Testing, Multilingual Simulation, Automated RCA",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS — restrict to known origins when API_ALLOWED_ORIGINS is set ──────────
_allowed_origins = [o.strip() for o in settings.api_allowed_origins.split(",") if o.strip()] \
    if settings.api_allowed_origins else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API key authentication middleware ─────────────────────────────────────────
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """
    Require X-API-Key header when VYUHA_API_KEY is configured.
    /health is always public for load balancer probes.
    """
    if request.url.path == "/health":
        return await call_next(request)

    if settings.vyuha_api_key:
        provided = request.headers.get("X-API-Key", "")
        if not provided:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing X-API-Key header"},
            )
        if provided != settings.vyuha_api_key:
            log.warning("api_key_rejected", path=request.url.path)
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Invalid API key"},
            )

    return await call_next(request)

app.include_router(test_cases.router, prefix="/test-cases", tags=["Test Cases"])
app.include_router(runs.router, prefix="/runs", tags=["Test Runs"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
app.include_router(generate.router, prefix="/generate", tags=["Generation"])
app.include_router(ingest.router, prefix="/ingest", tags=["Ingestion"])
app.include_router(audio.router, prefix="/test-cases", tags=["Audio"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "vyuha"}
