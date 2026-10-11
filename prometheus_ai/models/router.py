"""Model Router and Factory for Multi-Vendor Provider Instantiation.

Dynamically creates and routes model calls based on validated application settings
or model identifier strings, supporting:
- Anthropic Claude
- OpenAI Cloud
- Local inference (Ollama / vLLM)
- Deterministic Mocks
"""

from typing import Any

from prometheus_ai.models.anthropic_provider import AnthropicProvider
from prometheus_ai.models.budget import BudgetLimits, BudgetTracker
from prometheus_ai.models.exceptions import ModelConfigurationError
from prometheus_ai.models.gemini_provider import GeminiProvider
from prometheus_ai.models.mock_provider import MockModelProvider
from prometheus_ai.models.openai_provider import OpenAIProvider
from prometheus_ai.models.provider import BaseModelProvider
from services.api.config import Settings, get_settings


class ModelRouter:
    """Factory and routing coordinator for LLM providers."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def create_budget_tracker(
        self,
        max_calls: int | None = None,
        max_elapsed_seconds: float | None = None,
        max_total_tokens: int | None = None,
        max_cost_usd: float | None = None,
        max_retries: int | None = None,
        max_response_bytes: int | None = None,
        timeout_seconds: float | None = None,
    ) -> BudgetTracker:
        """Create a configured BudgetTracker using system settings and optional overrides."""
        limits = BudgetLimits(
            max_calls=max_calls if max_calls is not None else self.settings.MODEL_MAX_CALLS_PER_RUN,
            max_elapsed_seconds=max_elapsed_seconds
            if max_elapsed_seconds is not None
            else self.settings.MODEL_MAX_RUN_TIME_SECONDS,
            max_total_tokens=max_total_tokens
            if max_total_tokens is not None
            else self.settings.MODEL_MAX_TOTAL_TOKENS,
            max_estimated_cost_usd=max_cost_usd
            if max_cost_usd is not None
            else self.settings.MODEL_MAX_ESTIMATED_COST_USD,
            max_retries=max_retries if max_retries is not None else self.settings.MODEL_MAX_RETRIES,
            max_response_bytes=max_response_bytes
            if max_response_bytes is not None
            else self.settings.MODEL_MAX_RESPONSE_BYTES,
            timeout_seconds=timeout_seconds
            if timeout_seconds is not None
            else self.settings.MODEL_TIMEOUT_SECONDS,
        )
        return BudgetTracker(limits=limits)

    def get_provider(
        self,
        model_id: str | None = None,
        budget_tracker: BudgetTracker | None = None,
        **overrides: Any,
    ) -> BaseModelProvider:
        """Instantiate a provider adapter for the requested model identifier.

        Args:
            model_id: e.g., 'anthropic/claude-3-5-sonnet-20241022', 'openai/gpt-4o',
                      'local/qwen2.5-coder:7b', or 'mock/test-model'.
                      If omitted, defaults to settings.DEFAULT_MODEL.
            budget_tracker: Optional budget monitor to attach.
            overrides: Optional credential or endpoint overrides.
        """
        target = model_id or self.settings.DEFAULT_MODEL
        target_lower = target.lower()

        # Parse prefix or model family
        if target_lower.startswith("mock") or target_lower == "mock":
            model_name = target.split("/", 1)[1] if "/" in target else "mock-agent-model"
            return MockModelProvider(
                model_name=model_name,
                default_timeout=self.settings.MODEL_TIMEOUT_SECONDS,
                max_retries=self.settings.MODEL_MAX_RETRIES,
                budget_tracker=budget_tracker,
                **overrides,
            )

        if target_lower.startswith("anthropic/") or "claude" in target_lower:
            model_name = target.split("/", 1)[1] if "/" in target else target
            api_key = overrides.get("api_key") or self.settings.ANTHROPIC_API_KEY
            auth_token = overrides.get("auth_token") or self.settings.ANTHROPIC_AUTH_TOKEN
            base_url = overrides.get("base_url") or self.settings.ANTHROPIC_BASE_URL

            return AnthropicProvider(
                model_name=model_name,
                api_key=api_key,
                auth_token=auth_token,
                base_url=base_url,
                default_timeout=self.settings.MODEL_TIMEOUT_SECONDS,
                max_retries=self.settings.MODEL_MAX_RETRIES,
                budget_tracker=budget_tracker,
            )

        if target_lower.startswith("local/") or "ollama" in target_lower or "qwen" in target_lower:
            model_name = target.split("/", 1)[1] if "/" in target else self.settings.LOCAL_LLM_MODEL
            base_url = overrides.get("base_url") or self.settings.LOCAL_LLM_BASE_URL
            return OpenAIProvider(
                model_name=model_name,
                api_key=overrides.get("api_key") or "local",
                base_url=base_url,
                provider_name="local",
                default_timeout=self.settings.MODEL_TIMEOUT_SECONDS,
                max_retries=self.settings.MODEL_MAX_RETRIES,
                budget_tracker=budget_tracker,
            )

        if (
            target_lower.startswith("openai/")
            or "gpt" in target_lower
            or target_lower.startswith("o1")
            or target_lower.startswith("o3")
        ):
            model_name = target.split("/", 1)[1] if "/" in target else target
            api_key = overrides.get("api_key") or self.settings.OPENAI_API_KEY
            base_url = overrides.get("base_url") or self.settings.OPENAI_BASE_URL
            return OpenAIProvider(
                model_name=model_name,
                api_key=api_key,
                base_url=base_url,
                provider_name="openai",
                default_timeout=self.settings.MODEL_TIMEOUT_SECONDS,
                max_retries=self.settings.MODEL_MAX_RETRIES,
                budget_tracker=budget_tracker,
            )

        if target_lower.startswith("gemini/") or "gemini" in target_lower:
            model_name = target.split("/", 1)[1] if "/" in target else target
            api_key = overrides.get("api_key") or self.settings.GEMINI_API_KEY
            base_url = overrides.get("base_url") or self.settings.GEMINI_BASE_URL
            return GeminiProvider(
                model_name=model_name,
                api_key=api_key,
                base_url=base_url,
                default_timeout=self.settings.MODEL_TIMEOUT_SECONDS,
                max_retries=self.settings.MODEL_MAX_RETRIES,
                budget_tracker=budget_tracker,
            )

        # Fallback or unknown provider prefix
        raise ModelConfigurationError(
            f"Unrecognized or unsupported model identifier: '{target}'. "
            "Supported prefixes: 'gemini/', 'anthropic/', 'openai/', 'local/', 'mock/'."
        )


def get_model_provider(
    model_id: str | None = None,
    budget_tracker: BudgetTracker | None = None,
    settings: Settings | None = None,
    **overrides: Any,
) -> BaseModelProvider:
    """Convenience factory returning a configured BaseModelProvider instance."""
    router = ModelRouter(settings=settings)
    return router.get_provider(
        model_id=model_id,
        budget_tracker=budget_tracker,
        **overrides,
    )
