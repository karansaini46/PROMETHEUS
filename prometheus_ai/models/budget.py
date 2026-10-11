"""Budget Tracking, Limits, and Cancellation Management for Model Invocations.

Enforces execution constraints per run:
- Maximum model calls
- Maximum elapsed execution time
- Maximum token usage
- Maximum estimated cost
- Maximum response size
- Cooperative cancellation
"""

import time
from dataclasses import dataclass, field
from typing import Any

from prometheus_ai.models.exceptions import (
    ModelBudgetExceededError,
    ModelCancelledError,
)
from prometheus_ai.models.types import ModelUsage


class CancellationToken:
    """Cooperative cancellation token for in-flight model operations."""

    def __init__(self) -> None:
        self._cancelled: bool = False
        self._reason: str | None = None

    def cancel(self, reason: str = "Operation cancelled by caller") -> None:
        """Mark this token as cancelled."""
        self._cancelled = True
        self._reason = reason

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        return self._cancelled

    def check_cancelled(self) -> None:
        """Raise ModelCancelledError if cancellation has been requested."""
        if self._cancelled:
            raise ModelCancelledError(
                f"Model execution was cancelled: {self._reason or 'User requested cancellation'}"
            )


@dataclass
class BudgetLimits:
    """Configurable boundaries for autonomous model execution."""

    max_calls: int | None = 50
    max_elapsed_seconds: float | None = 1800.0
    max_total_tokens: int | None = 500_000
    max_estimated_cost_usd: float | None = 10.0
    max_retries: int = 3
    max_response_bytes: int = 2_000_000
    timeout_seconds: float = 60.0


@dataclass
class BudgetTracker:
    """Monitors resource consumption and enforces budget guardrails."""

    limits: BudgetLimits = field(default_factory=BudgetLimits)
    calls_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    is_cost_estimated: bool = True
    start_time: float = field(default_factory=time.monotonic)

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed wall-clock time in seconds since tracker creation."""
        return time.monotonic() - self.start_time

    def check_pre_call(self) -> None:
        """Verify remaining budget before dispatching a model request.

        Raises:
            ModelBudgetExceededError: If any execution constraint is exhausted.
        """
        # 1. Call limit check
        if self.limits.max_calls is not None and self.calls_count >= self.limits.max_calls:
            raise ModelBudgetExceededError(
                f"Exceeded maximum model calls: {self.calls_count}/{self.limits.max_calls} calls executed",
                details={"calls_count": self.calls_count, "max_calls": self.limits.max_calls},
            )

        # 2. Elapsed time check
        elapsed = self.elapsed_seconds
        if (
            self.limits.max_elapsed_seconds is not None
            and elapsed > self.limits.max_elapsed_seconds
        ):
            raise ModelBudgetExceededError(
                f"Exceeded maximum execution time: {elapsed:.2f}s elapsed (limit: {self.limits.max_elapsed_seconds}s)",
                details={
                    "elapsed_seconds": elapsed,
                    "max_elapsed_seconds": self.limits.max_elapsed_seconds,
                },
            )

        # 3. Token budget check
        if (
            self.limits.max_total_tokens is not None
            and self.total_tokens >= self.limits.max_total_tokens
        ):
            raise ModelBudgetExceededError(
                f"Exceeded maximum token budget: {self.total_tokens}/{self.limits.max_total_tokens} tokens consumed",
                details={
                    "total_tokens": self.total_tokens,
                    "max_total_tokens": self.limits.max_total_tokens,
                },
            )

        # 4. Cost budget check
        if (
            self.limits.max_estimated_cost_usd is not None
            and self.estimated_cost_usd >= self.limits.max_estimated_cost_usd
        ):
            raise ModelBudgetExceededError(
                f"Exceeded estimated cost budget: ${self.estimated_cost_usd:.4f} (limit: ${self.limits.max_estimated_cost_usd:.2f})",
                details={
                    "estimated_cost_usd": self.estimated_cost_usd,
                    "max_estimated_cost_usd": self.limits.max_estimated_cost_usd,
                },
            )

    def record_usage(self, usage: ModelUsage, response_bytes: int = 0) -> None:
        """Record usage from a completed request and enforce response constraints.

        Args:
            usage: The ModelUsage object reported from the provider.
            response_bytes: Byte length of the returned response content.

        Raises:
            ModelBudgetExceededError: If response size or updated budgets are violated.
        """
        # Response size check
        if (
            self.limits.max_response_bytes is not None
            and response_bytes > self.limits.max_response_bytes
        ):
            raise ModelBudgetExceededError(
                f"Model response size ({response_bytes} bytes) exceeded maximum allowed limit ({self.limits.max_response_bytes} bytes)",
                details={
                    "response_bytes": response_bytes,
                    "max_response_bytes": self.limits.max_response_bytes,
                },
            )

        self.calls_count += 1
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        self.estimated_cost_usd += usage.estimated_cost_usd
        self.is_cost_estimated = True

    def get_summary(self) -> dict[str, Any]:
        """Return a structured diagnostic summary of consumption."""
        return {
            "calls_count": self.calls_count,
            "max_calls": self.limits.max_calls,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "max_elapsed_seconds": self.limits.max_elapsed_seconds,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "max_total_tokens": self.limits.max_total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "max_estimated_cost_usd": self.limits.max_estimated_cost_usd,
            "is_cost_estimated": True,
        }
