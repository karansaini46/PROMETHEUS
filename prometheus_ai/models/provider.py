"""Model Provider Abstraction and Protocols."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ModelUsage:
    """Token consumption and cost accounting."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float = 0.0


@dataclass
class ModelResponse:
    """Standardized response from an LLM provider."""

    content: str
    model: str
    usage: ModelUsage
    tool_calls: list[dict[str, Any]] | None = None


class BaseModelProvider(ABC):
    """Abstract protocol for multi-vendor LLM routing."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> ModelResponse:
        """Generate a completion from the underlying model."""
        raise NotImplementedError(
            "Milestone 2 Deliverable: Model provider adapter not yet configured."
        )
