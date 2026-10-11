"""Google Gemini Provider Adapter.

Implements BaseModelProvider for Google Gemini models (Gemini 2.0 Flash, Gemini 1.5 Flash,
Gemini 1.5 Pro) utilizing Google's official OpenAI-compatible endpoint:
https://generativelanguage.googleapis.com/v1beta/openai/

Supports:
- Gemini Free Plan (15 RPM / 1M TPM / 1500 RPD on Google AI Studio)
- Native Structured Outputs and Tool / Function Calling
- Free tier token accounting ($0.00 cost) and quota error normalization
"""

from prometheus_ai.models.budget import BudgetTracker
from prometheus_ai.models.openai_provider import OpenAIProvider


class GeminiProvider(OpenAIProvider):
    """Adapter for Google Gemini models via OpenAI-compatible endpoint."""

    DEFAULT_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(
        self,
        model_name: str = "gemini-2.0-flash",
        api_key: str | None = None,
        base_url: str | None = None,
        default_timeout: float = 60.0,
        max_retries: int = 3,
        budget_tracker: BudgetTracker | None = None,
    ) -> None:
        endpoint = base_url or self.DEFAULT_BASE_URL
        # Model identifier mapping: strip 'gemini/' prefix if passed
        resolved_model = model_name.split("/", 1)[1] if "/" in model_name else model_name
        super().__init__(
            model_name=resolved_model,
            api_key=api_key,
            base_url=endpoint,
            provider_name="gemini",
            default_timeout=default_timeout,
            max_retries=max_retries,
            budget_tracker=budget_tracker,
        )
