from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database — Railway provides postgresql:// or postgres://, we normalise to +asyncpg
    database_url: str = "postgresql+asyncpg://vyuha:vyuha@localhost:5432/vyuha"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM Judges
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # TTS
    sarvam_api_key: str = ""
    azure_speech_key: str = ""
    azure_speech_region: str = "eastus"
    elevenlabs_api_key: str = ""

    # STT — local Whisper server (local_whisper_server.py or any OpenAI-compatible STT)
    # Set to tunnel URL when API runs on Railway (e.g. https://xyz.trycloudflare.com)
    ollama_url: str = ""          # STT server URL (exposes /v1/audio/transcriptions)
    ollama_stt_model: str = "whisper"   # model name passed to the STT server

    # LLM turn-formatting — separate Ollama instance for agent/user labelling
    # Set OLLAMA_LLM_URL to the Ollama server URL (separate from STT server)
    # e.g. https://abc.trycloudflare.com → http://localhost:11434
    ollama_llm_url: str = ""      # Ollama LLM URL; "" = skip turn-formatting
    ollama_llm_model: str = "llama3.2"  # model to use for turn-formatting

    # Other STT providers (future)
    deepgram_api_key: str = ""

    # VAUT connection
    vaut_websocket_url: str = "ws://localhost:8765"

    # Scoring thresholds
    eva_a_pass_threshold: float = 0.85
    regression_pass_rate: float = 0.97
    latency_p95_threshold_ms: float = 800.0
    hallucination_rate_threshold: float = 0.02

    # Judge models
    default_judge_model: str = "claude-sonnet-4-6"
    fallback_judge_model: str = "gpt-4o"

    # Audio file storage (pre-uploaded audio per conversation node, bypasses TTS)
    audio_storage_path: str = "/tmp/vyuha/audio"

    # Test execution
    default_k_runs: int = 3
    max_concurrent_runs: int = 500

    @model_validator(mode="after")
    def normalise_db_url(self) -> "Settings":
        url = self.database_url
        # Railway provides postgres:// or postgresql:// — asyncpg requires +asyncpg dialect
        if url.startswith("postgres://"):
            self.database_url = "postgresql+asyncpg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            self.database_url = "postgresql+asyncpg://" + url[len("postgresql://"):]
        return self


settings = Settings()
