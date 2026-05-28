from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(test_cases.router, prefix="/test-cases", tags=["Test Cases"])
app.include_router(runs.router, prefix="/runs", tags=["Test Runs"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
app.include_router(generate.router, prefix="/generate", tags=["Generation"])
app.include_router(ingest.router, prefix="/ingest", tags=["Ingestion"])
app.include_router(audio.router, prefix="/test-cases", tags=["Audio"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "vyuha"}
