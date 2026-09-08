"""Central application configuration, loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "FrontDesk Voice AI"
    log_level: str = "INFO"
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://voiceops:voiceops@localhost:5432/voiceops"

    # LLM (Ollama)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: float = 30.0

    # Speech-to-text (faster-whisper)
    whisper_model: str = "base.en"
    whisper_device: str = "auto"

    # Text-to-speech (Piper)
    piper_voice: str = "en_US-lessac-medium"
    piper_model_path: str = "./voice-models/piper"

    # WebSocket / audio
    audio_sample_rate: int = 16000

    # Tools
    tool_timeout_seconds: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
