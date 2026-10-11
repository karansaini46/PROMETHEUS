"""Deterministic Mock Provider for Unit Tests and Offline Validation.

Guarantees deterministic agent evaluations. Every response generated is explicitly
tagged with `is_mock=True` to ensure mock results are never mistaken for real model performance.
"""

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from prometheus_ai.models.budget import BudgetTracker
from prometheus_ai.models.exceptions import (
    ModelAuthenticationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from prometheus_ai.models.provider import BaseModelProvider
from prometheus_ai.models.types import ModelResponse, ModelUsage, ToolCallRequest

T = TypeVar("T", bound=BaseModel)


class MockModelProvider(BaseModelProvider):
    """Deterministic mock model provider for reproducible testing."""

    def __init__(
        self,
        model_name: str = "mock-claude-3-5",
        default_response_text: str = "Mock generated text response.",
        simulated_usage: ModelUsage | None = None,
        default_timeout: float = 60.0,
        max_retries: int = 3,
        budget_tracker: BudgetTracker | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            provider_name="mock",
            default_timeout=default_timeout,
            max_retries=max_retries,
            budget_tracker=budget_tracker,
        )
        self.default_response_text = default_response_text
        self.simulated_usage = simulated_usage or ModelUsage(
            prompt_tokens=25,
            completion_tokens=50,
            total_tokens=75,
            estimated_cost_usd=0.0001,
            is_cost_estimated=True,
        )
        # Queues for sequenced testing
        self.response_queue: list[ModelResponse | Exception] = []
        self.structured_queue: list[Any | Exception] = []
        self.call_history: list[dict[str, Any]] = []

        # Simulation behavior flags
        self.simulated_delay_seconds: float = 0.0
        self.should_timeout: bool = False
        self.should_rate_limit_count: int = 0
        self.should_auth_fail: bool = False
        self.canned_tool_calls: list[ToolCallRequest] | None = None
        self.custom_handler: Callable[..., Any] | None = None

    def queue_response(self, response_or_exc: ModelResponse | Exception) -> None:
        """Enqueue a response or error for sequential generation."""
        self.response_queue.append(response_or_exc)

    def queue_structured(self, result_or_exc: Any | Exception) -> None:
        """Enqueue a structured object or error for sequential structured generation."""
        self.structured_queue.append(result_or_exc)

    async def _execute_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        timeout: float | None = None,
    ) -> ModelResponse:
        self.call_history.append(
            {
                "type": "text",
                "prompt": prompt,
                "system_prompt": system_prompt,
                "tools": tools,
                "temperature": temperature,
                "timeout": timeout,
            }
        )

        if self.should_auth_fail:
            raise ModelAuthenticationError(
                "Mock authentication failure", provider=self.provider_name
            )

        if self.should_rate_limit_count > 0:
            self.should_rate_limit_count -= 1
            raise ModelRateLimitError(
                "Mock rate limit exceeded (HTTP 429)", provider=self.provider_name
            )

        if self.should_timeout:
            raise ModelTimeoutError("Mock call timed out", provider=self.provider_name)

        if self.simulated_delay_seconds > 0:
            await asyncio.sleep(self.simulated_delay_seconds)

        if self.custom_handler:
            return cast(
                ModelResponse,
                self.custom_handler(prompt=prompt, system_prompt=system_prompt, tools=tools),
            )

        if self.response_queue:
            item = self.response_queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        return ModelResponse(
            content=self.default_response_text,
            model=self.model_name,
            provider="mock",
            usage=self.simulated_usage,
            tool_calls=self.canned_tool_calls,
            is_mock=True,
            finish_reason="stop",
        )

    async def _execute_generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        timeout: float | None = None,
    ) -> tuple[T, ModelResponse]:
        self.call_history.append(
            {
                "type": "structured",
                "prompt": prompt,
                "schema": response_schema.__name__,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "timeout": timeout,
            }
        )

        if self.should_auth_fail:
            raise ModelAuthenticationError(
                "Mock authentication failure", provider=self.provider_name
            )

        if self.should_rate_limit_count > 0:
            self.should_rate_limit_count -= 1
            raise ModelRateLimitError(
                "Mock rate limit exceeded (HTTP 429)", provider=self.provider_name
            )

        if self.should_timeout:
            raise ModelTimeoutError("Mock call timed out", provider=self.provider_name)

        if self.simulated_delay_seconds > 0:
            await asyncio.sleep(self.simulated_delay_seconds)

        if self.structured_queue:
            item = self.structured_queue.pop(0)
            if isinstance(item, Exception):
                raise item
            if isinstance(item, str):
                parsed = self._parse_and_validate_json(item, response_schema)
                raw_content = item
            elif isinstance(item, dict):
                try:
                    parsed = response_schema.model_validate(item)
                    raw_content = parsed.model_dump_json()
                except Exception as exc:
                    raise ModelInvalidResponseError(
                        f"Mock dict failed schema validation for {response_schema.__name__}: {exc}",
                        provider=self.provider_name,
                        model=self.model_name,
                    ) from exc
            elif isinstance(item, response_schema):
                parsed = item
                raw_content = item.model_dump_json()
            else:
                raise ModelInvalidResponseError(
                    f"Mock item {type(item)} does not match schema {response_schema.__name__}",
                    provider=self.provider_name,
                )

            resp = ModelResponse(
                content=raw_content,
                model=self.model_name,
                provider="mock",
                usage=self.simulated_usage,
                is_mock=True,
                finish_reason="stop",
            )
            return parsed, resp

        # Default fallback: try to parse default_response_text
        try:
            parsed = self._parse_and_validate_json(self.default_response_text, response_schema)
            resp = ModelResponse(
                content=self.default_response_text,
                model=self.model_name,
                provider="mock",
                usage=self.simulated_usage,
                is_mock=True,
                finish_reason="stop",
            )
            return parsed, resp
        except Exception as exc:
            raise ModelInvalidResponseError(
                f"Default mock response cannot be validated against {response_schema.__name__}: {exc}",
                provider=self.provider_name,
            ) from exc
