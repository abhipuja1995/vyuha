#!/usr/bin/env python3
"""
Minimal local STT server — exposes OpenAI-compatible /v1/audio/transcriptions
so the Vyuha backend (OllamaSTT) can call it without any code changes.

Usage:
    python local_whisper_server.py [--model tiny|base|small|medium|large-v3] [--port 11435]

Point OLLAMA_URL at this server:
    OLLAMA_URL=http://localhost:11435
    OLLAMA_STT_MODEL=base        # any value — the server ignores it and uses --model

Models (auto-downloaded on first use, ~150MB for base):
    tiny   — fastest, lowest accuracy
    base   — good balance for Indian-accented call-centre audio  (recommended)
    small  — better accuracy, ~500MB
    medium — near-human, ~1.5GB
    large-v3 — best quality, ~3GB
"""

import argparse
import io
import os
import tempfile
import threading
import time

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

# Lazily loaded so startup is instant
_model = None
_model_name = "base"
_model_lock = threading.Lock()


def get_model(name: str):
    global _model, _model_name
    with _model_lock:
        if _model is None or _model_name != name:
            from faster_whisper import WhisperModel

            print(f"Loading Whisper model '{name}' (downloads on first use)…")
            _model = WhisperModel(name, device="cpu", compute_type="int8")
            _model_name = name
            print("Model ready.")
    return _model


app = FastAPI(title="Local Whisper STT", version="1.0")


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default="base"),
    language: str = Form(default=""),
):
    audio_bytes = await file.read()
    if not audio_bytes:
        return JSONResponse(
            {"error": {"message": "audio file is empty", "type": "invalid_request_error"}},
            status_code=400,
        )

    # Write to a temp file (faster-whisper needs a file path)
    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    # Normalise language code: "en-IN" → "en", "hi" → "hi", "" → None (auto-detect)
    whisper_lang = language.split("-")[0].lower() if language else None

    try:
        whisper = get_model(_model_name)  # uses CLI --model, not the form field
        segments, info = whisper.transcribe(tmp_path, beam_size=5, language=whisper_lang)
        text = " ".join(seg.text.strip() for seg in segments).strip()
    finally:
        os.unlink(tmp_path)

    return {"text": text, "language": info.language}


@app.get("/health")
async def health():
    return {"status": "ok", "model": _model_name}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local Whisper STT server")
    parser.add_argument("--model", default="base", help="Whisper model size")
    parser.add_argument("--port", type=int, default=11435, help="Port to listen on")
    args = parser.parse_args()

    _model_name = args.model
    print(f"Starting local Whisper STT server on port {args.port}")
    print(f"Model: {args.model} (will download on first request if not cached)")
    print(f"Set in Railway: OLLAMA_URL=http://<your-tunnel>:{args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)
