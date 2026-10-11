"""Unit Tests for ModelRouter and Dynamic Provider Dispatch."""

import pytest

from prometheus_ai.models.anthropic_provider import AnthropicProvider
from prometheus_ai.models.exceptions import ModelConfigurationError
from prometheus_ai.models.mock_provider import MockModelProvider
from prometheus_ai.models.openai_provider import OpenAIProvider
from prometheus_ai.models.router import ModelRouter, get_model_provider
from services.api.config import Settings


@pytest.mark.unit
def test_router_resolves_mock_provider() -> None:
    """Verify router instantiates MockModelProvider for mock prefixes."""
    provider = get_model_provider("mock/test-engine")
    assert isinstance(provider, MockModelProvider)
    assert provider.model_name == "test-engine"
    assert provider.provider_name == "mock"


@pytest.mark.unit
def test_router_resolves_anthropic_provider() -> None:
    """Verify router instantiates AnthropicProvider for Anthropic model IDs."""
    provider = get_model_provider(
        "anthropic/claude-3-5-sonnet-20241022",
        api_key="test-dummy-key",
    )
    assert isinstance(provider, AnthropicProvider)
    assert provider.model_name == "claude-3-5-sonnet-20241022"
    assert provider.provider_name == "anthropic"


@pytest.mark.unit
def test_router_resolves_openai_provider() -> None:
    """Verify router instantiates OpenAIProvider for OpenAI model IDs."""
    provider = get_model_provider(
        "openai/gpt-4o",
        api_key="test-dummy-key",
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider.model_name == "gpt-4o"
    assert provider.provider_name == "openai"


@pytest.mark.unit
def test_router_resolves_local_provider() -> None:
    """Verify router instantiates OpenAIProvider targeting local endpoints for local/qwen models."""
    provider = get_model_provider(
        "local/qwen2.5-coder:7b",
        base_url="http://localhost:11434/v1",
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider.model_name == "qwen2.5-coder:7b"
    assert provider.provider_name == "local"
    assert provider.base_url == "http://localhost:11434/v1"


@pytest.mark.unit
def test_router_unrecognized_model_raises_configuration_error() -> None:
    """Verify unknown model prefix raises ModelConfigurationError."""
    with pytest.raises(ModelConfigurationError) as exc_info:
        get_model_provider("unsupported-vendor/unknown-model")

    assert "Unrecognized or unsupported model identifier" in str(exc_info.value)


@pytest.mark.unit
def test_router_attaches_configured_budget_tracker() -> None:
    """Verify router creates and attaches BudgetTracker with configured boundaries."""
    settings = Settings(
        MODEL_MAX_CALLS_PER_RUN=15,
        MODEL_MAX_TOTAL_TOKENS=50000,
        MODEL_MAX_ESTIMATED_COST_USD=2.50,
    )
    router = ModelRouter(settings=settings)
    tracker = router.create_budget_tracker()
    provider = router.get_provider("mock/agent-eval", budget_tracker=tracker)

    assert provider.budget_tracker is not None
    assert provider.budget_tracker.limits.max_calls == 15
    assert provider.budget_tracker.limits.max_total_tokens == 50000
    assert provider.budget_tracker.limits.max_estimated_cost_usd == 2.50
