"""Centralized configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent

# Models currently available on Groq free/developer tier for this project.
# (Kimi K2 / Qwen3-32B were removed from many accounts — use replacements below.)
AvailableModel = Literal[
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
]

AVAILABLE_MODELS: tuple[AvailableModel, ...] = (
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
)

MODEL_LABELS: dict[str, str] = {
    "openai/gpt-oss-120b": "GPT-OSS 120B (default)",
    "qwen/qwen3.6-27b": "Qwen 3.6 27B",
    "openai/gpt-oss-20b": "GPT-OSS 20B (faster)",
}


class Settings(BaseSettings):
    """Application settings from `.env` / process environment."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_default_model: str = Field(
        default="openai/gpt-oss-120b",
        alias="GROQ_DEFAULT_MODEL",
    )
    generated_projects_dir: str = Field(
        default="generated_projects",
        alias="GENERATED_PROJECTS_DIR",
    )
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )
    agent_recursion_limit: int = Field(default=100, alias="AGENT_RECURSION_LIMIT")
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")

    @property
    def projects_root(self) -> Path:
        path = Path(self.generated_projects_dir)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
