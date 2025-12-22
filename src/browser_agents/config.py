"""Configuration via pydantic-settings with .env support."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Follows the pattern from ../ai-agents/src/core/config.py.

    Usage:
        from browser_agents.config import settings
        print(settings.local_model)  # gpt-oss:120b
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Configuration (Ollama)
    local_model: str = Field(
        default="gpt-oss:120b",
        description="Ollama model name for LLM calls",
    )
    ollama_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API URL",
    )


# Singleton instance
settings = Settings()
