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

    # STT — Ollama/Whisper (any OpenAI-compatible /v1/audio/transcriptions endpoint)
    # host.docker.internal:11434 reaches the Mac host from inside Docker
    ollama_url: str = ""          # STT server URL
    ollama_stt_model: str = "whisper"

    # LLM turn-formatting via local Ollama
    ollama_llm_url: str = ""      # Ollama LLM URL; "" = skip turn-formatting
    ollama_llm_model: str = "llama3.2"

    # Local LLM judge — overrides Anthropic/OpenAI for scoring when set
    # Must expose an OpenAI-compatible /v1/chat/completions endpoint
    local_llm_url: str = ""       # e.g. http://host.docker.internal:11434/v1
    local_llm_model: str = "llama3.2"

    # Local TTS — any OpenAI-compatible /v1/audio/speech endpoint
    # e.g. openedai-speech, kokoro-fastapi running on the host
    local_tts_url: str = ""       # e.g. http://host.docker.internal:8880
    local_tts_model: str = "tts-1"
    local_tts_voice: str = "alloy"

    # Other STT providers
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

    # Security — set VYUHA_API_KEY to enable API key auth on all endpoints
    vyuha_api_key: str = ""
    # Comma-separated allowed CORS origins, e.g. "http://localhost:3000,https://vyuha.example.com"
    # Leave empty to allow all origins (not recommended for production)
    api_allowed_origins: str = ""

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
