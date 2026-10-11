"""Normalized Exception Hierarchy for PROMETHEUS Model Providers.

Provides vendor-independent error classification and ensures secrets are scrubbed
from error messages.
"""

from typing import Any

from prometheus_ai.models.sanitizer import sanitize_secrets


class ModelError(Exception):
    """Base exception for all model provider errors."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        model: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.raw_message = message
        self.sanitized_message = sanitize_secrets(message)
        self.provider = provider
        self.model = model
        self.details = details or {}
        super().__init__(self.sanitized_message)

    def __str__(self) -> str:
        ctx = f"[{self.provider}/{self.model}] " if self.provider and self.model else ""
        return f"{ctx}{self.sanitized_message}"


class ModelAuthenticationError(ModelError):
    """Raised when authentication fails (HTTP 401/403 or invalid credentials)."""

    pass


class ModelRateLimitError(ModelError):
    """Raised when provider rate limits or token capacity is exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        model: str | None = None,
        retry_after_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, provider=provider, model=model, details=details)
        self.retry_after_seconds = retry_after_seconds


class ModelTimeoutError(ModelError):
    """Raised when a model request times out."""

    pass


class ModelCancelledError(ModelError):
    """Raised when a model call is explicitly cancelled."""

    pass


class ModelContextLengthError(ModelError):
    """Raised when the prompt exceeds the model's maximum context window."""

    pass


class ModelInvalidResponseError(ModelError):
    """Raised when a response is malformed, unparseable, or fails schema validation."""

    pass


class ModelBudgetExceededError(ModelError):
    """Raised when execution limits (calls, time, tokens, cost) are exceeded."""

    pass


class ModelServiceUnavailableError(ModelError):
    """Raised on provider server outages (HTTP 500, 502, 503, 504) or connection errors."""

    pass


class ModelConfigurationError(ModelError):
    """Raised when provider settings, keys, or endpoints are improperly configured."""

    pass
