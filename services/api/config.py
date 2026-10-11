"""PROMETHEUS System Configuration & Environment Validation.

Uses Pydantic v2 Settings to validate all runtime configuration from
environment variables or .env files with strict typing and security guards.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the PROMETHEUS platform."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Application Environment
    PROMETHEUS_ENV: Literal["development", "test", "production"] = Field(
        default="development",
        description="Deployment stage",
    )
    API_HOST: str = Field(default="0.0.0.0", description="API server bind host")
    API_PORT: int = Field(default=8000, description="API server bind port")
    API_SECRET_KEY: str = Field(
        default="dev-secret-key-replace-with-secure-value-in-production-min-32-chars",
        description="Internal encryption and authentication key",
    )
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )

    # Database & Storage
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://prometheus:prometheus@localhost:5432/prometheus_db",
        description="Async PostgreSQL connection URL",
    )
    DATABASE_POOL_SIZE: int = Field(default=10, description="Async engine connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=5, description="Max overflow connections")
    ENABLE_VECTOR_SEARCH: bool = Field(
        default=False,
        description="Toggle vector search features; disabled by default for graceful degradation",
    )

    # Model Provider Routing
    DEFAULT_MODEL: str = Field(
        default="anthropic/claude-3-5-sonnet-20241022",
        description="Default model identifier",
    )
    ANTHROPIC_API_KEY: str | None = Field(default=None, description="Anthropic API Key")
    ANTHROPIC_AUTH_TOKEN: str | None = Field(default=None, description="Anthropic Auth Token")
    ANTHROPIC_BASE_URL: str | None = Field(default=None, description="Anthropic API base URL override")
    OPENAI_API_KEY: str | None = Field(default=None, description="OpenAI API Key")
    OPENAI_BASE_URL: str | None = Field(default=None, description="OpenAI API base URL override")
    LOCAL_LLM_BASE_URL: str = Field(
        default="http://localhost:11434/v1",
        description="OpenAI-compatible local inference endpoint (Ollama/vLLM)",
    )
    LOCAL_LLM_MODEL: str = Field(
        default="qwen2.5-coder:7b",
        description="Local inference model name",
    )

    # Model Budgets & Reliability Controls
    MODEL_MAX_CALLS_PER_RUN: int = Field(default=50, description="Max LLM calls permitted per debugging run")
    MODEL_TIMEOUT_SECONDS: float = Field(default=60.0, description="Per-request model timeout in seconds")
    MODEL_MAX_RETRIES: int = Field(default=3, description="Maximum retries for transient provider errors")
    MODEL_MAX_RUN_TIME_SECONDS: float = Field(default=1800.0, description="Max cumulative execution time per run")
    MODEL_MAX_TOTAL_TOKENS: int | None = Field(default=500_000, description="Max tokens permitted per run")
    MODEL_MAX_ESTIMATED_COST_USD: float | None = Field(default=10.0, description="Max estimated cost in USD per run")
    MODEL_MAX_RESPONSE_BYTES: int = Field(default=2_000_000, description="Max model response payload size in bytes")

    # Execution Sandbox & Worktrees
    DOCKER_HOST: str = Field(
        default="unix:///var/run/docker.sock",
        description="Docker daemon socket URI",
    )
    SANDBOX_IMAGE: str = Field(
        default="prometheus-sandbox:latest",
        description="Base Docker image for execution sandboxes",
    )
    SANDBOX_TIMEOUT_SECONDS: int = Field(
        default=300,
        description="Maximum seconds a sandbox container may execute",
    )
    SANDBOX_MEMORY_LIMIT: str = Field(
        default="4g",
        description="Memory limit for sandbox containers",
    )
    SANDBOX_CPU_LIMIT: float = Field(
        default=2.0,
        description="CPU core limit for sandbox containers",
    )
    SANDBOX_PIDS_LIMIT: int = Field(
        default=256,
        description="Process/thread count limit to prevent fork bombs",
    )
    WORKTREE_BASE_DIR: str = Field(
        default="./data/worktrees",
        description="Filesystem root where isolated git worktrees are mounted",
    )

    # Observability & Tracing
    OTEL_SERVICE_NAME: str = Field(
        default="prometheus-api",
        description="OpenTelemetry service name",
    )
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = Field(
        default=None,
        description="OTLP collector endpoint (e.g. http://localhost:4317)",
    )
    OTEL_EXPORTER_ENABLED: bool = Field(
        default=False,
        description="Enable OpenTelemetry remote span exporting",
    )

    @field_validator("API_SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info: object) -> str:
        """Validate secret key strength in production."""
        if len(v) < 16:
            raise ValueError("API_SECRET_KEY must be at least 16 characters long.")
        return v

    @field_validator("SANDBOX_PIDS_LIMIT")
    @classmethod
    def validate_pids_limit(cls, v: int) -> int:
        """Ensure sandbox pid limit is within safe boundaries."""
        if v < 16 or v > 2048:
            raise ValueError(
                "SANDBOX_PIDS_LIMIT must be between 16 and 2048 to prevent fork-bombs."
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
