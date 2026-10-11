"""Model Data Structures, Usage Tracking, and Rate Cards.

Standardizes token usage, estimated costs, tool calls, and model responses
across multiple LLM vendors.
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

# Standard cost per million tokens (prompt, completion) as of late 2024 / 2025
# Used ONLY for estimation. Estimated costs are always explicitly flagged.
MODEL_RATE_CARD_PER_1M: dict[str, tuple[float, float]] = {
    # Anthropic models (USD per 1M tokens)
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-sonnet-20240620": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (1.00, 5.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-opus-20240229": (15.00, 75.00),
    # OpenAI models
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-2024-08-06": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o1-preview": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    # Local / open-source default (free or marginal hosting)
    "qwen2.5-coder:7b": (0.0, 0.0),
    "deepseek-coder": (0.0, 0.0),
    # Google Gemini Free Tier models ($0.00 / free tier on Google AI Studio)
    "gemini-2.0-flash": (0.0, 0.0),
    "gemini-1.5-flash": (0.0, 0.0),
    "gemini-1.5-pro": (0.0, 0.0),
    "gemini-2.5-flash": (0.0, 0.0),
    "gemini-flash": (0.0, 0.0),
}


def calculate_estimated_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> tuple[float, bool]:
    """Calculate estimated cost in USD based on standard published rate cards.

    Returns:
        tuple[float, bool]: (estimated_cost_usd, is_cost_estimated)
    """
    clean_model = model.split("/")[-1].lower()

    # Try exact match, then prefix match
    rate = MODEL_RATE_CARD_PER_1M.get(clean_model)
    if rate is None:
        for known_model, rates in MODEL_RATE_CARD_PER_1M.items():
            if known_model in clean_model or clean_model in known_model:
                rate = rates
                break

    if rate is None:
        # Default fallback estimate (e.g., standard Claude 3.5 Sonnet tier)
        rate = (3.00, 15.00)

    prompt_cost = (prompt_tokens / 1_000_000.0) * rate[0]
    completion_cost = (completion_tokens / 1_000_000.0) * rate[1]
    total_cost = round(prompt_cost + completion_cost, 6)
    return total_cost, True


@dataclass
class ModelUsage:
    """Token consumption, cache statistics, and cost accounting.

    Attributes:
        prompt_tokens: Number of prompt/input tokens consumed.
        completion_tokens: Number of generated completion tokens.
        total_tokens: Sum of prompt and completion tokens.
        estimated_cost_usd: Estimated cost calculated via published rates.
        is_cost_estimated: Always True unless the provider directly reports billed cost.
        cache_read_tokens: Prompt caching read tokens where supported.
        cache_write_tokens: Prompt caching write tokens where supported.
        details: Additional provider-specific usage telemetry.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    is_cost_estimated: bool = True
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_counts(
        cls,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None = None,
        cache_read: int = 0,
        cache_write: int = 0,
        details: dict[str, Any] | None = None,
    ) -> "ModelUsage":
        """Instantiate usage, safely handling providers with partial token telemetry."""
        p_tok = prompt_tokens or 0
        c_tok = completion_tokens or 0
        t_tok = total_tokens if total_tokens is not None else (p_tok + c_tok)
        cost, is_est = calculate_estimated_cost(model, p_tok, c_tok)
        return cls(
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            total_tokens=t_tok,
            estimated_cost_usd=cost,
            is_cost_estimated=is_est,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            details=details or {},
        )


class ToolCallRequest(BaseModel):
    """Normalized structured tool call request emitted by a model."""

    call_id: str = Field(description="Unique identifier for the tool call")
    name: str = Field(description="Name of the tool to invoke")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Parsed tool invocation parameters",
    )
    reasoning: str | None = Field(
        default=None,
        description="Optional model reasoning for why this tool is called",
    )


@dataclass
class ModelResponse:
    """Standardized response from an LLM provider."""

    content: str
    model: str
    usage: ModelUsage
    tool_calls: list[ToolCallRequest] | None = None
    provider: str = "generic"
    finish_reason: str | None = None
    is_mock: bool = False
    raw_response: dict[str, Any] | None = None
