"""Base Protocol and Abstract Class for Model Providers.

Provides vendor-independent abstraction for:
- Text generation
- Structured Pydantic outputs
- Tool-call requests
- Token usage & cost accounting
- Timeouts & cooperative cancellation
- Provider error normalization & retry policies
"""

import asyncio
import json
import logging
import random
from abc import ABC, abstractmethod
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ValidationError

from prometheus_ai.models.budget import BudgetTracker, CancellationToken
from prometheus_ai.models.exceptions import (
    ModelCancelledError,
    ModelError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelServiceUnavailableError,
    ModelTimeoutError,
)
from prometheus_ai.models.sanitizer import sanitize_secrets
from prometheus_ai.models.types import ModelResponse

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseModelProvider(ABC):
    """Abstract protocol for multi-vendor LLM routing and structured outputs."""

    def __init__(
        self,
        model_name: str,
        provider_name: str = "generic",
        default_timeout: float = 60.0,
        max_retries: int = 3,
        budget_tracker: BudgetTracker | None = None,
    ) -> None:
        self.model_name = model_name
        self.provider_name = provider_name
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.budget_tracker = budget_tracker

    @property
    def model_id(self) -> str:
        """Fully qualified model identifier (e.g., 'anthropic/claude-3-5-sonnet-20241022')."""
        return f"{self.provider_name}/{self.model_name}"

    @abstractmethod
    async def _execute_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        timeout: float | None = None,
    ) -> ModelResponse:
        """Vendor-specific native text & tool generation implementation."""
        raise NotImplementedError

    @abstractmethod
    async def _execute_generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        timeout: float | None = None,
    ) -> tuple[T, ModelResponse]:
        """Vendor-specific native structured generation implementation."""
        raise NotImplementedError

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        timeout: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelResponse:
        """Generate a response with budget enforcement, retry policy, and cancellation guards."""
        if cancellation_token:
            cancellation_token.check_cancelled()

        if self.budget_tracker:
            self.budget_tracker.check_pre_call()

        req_timeout = timeout or self.default_timeout

        async def _call() -> ModelResponse:
            if cancellation_token:
                cancellation_token.check_cancelled()
            return await self._execute_generate(
                prompt=prompt,
                system_prompt=system_prompt,
                tools=tools,
                temperature=temperature,
                timeout=req_timeout,
            )

        response = cast(
            ModelResponse,
            await self._retry_with_backoff(_call, cancellation_token=cancellation_token),
        )

        if self.budget_tracker:
            response_bytes = len(response.content.encode("utf-8"))
            self.budget_tracker.record_usage(response.usage, response_bytes=response_bytes)

        return response

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        timeout: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[T, ModelResponse]:
        """Generate validated Pydantic structured output with strict error handling.

        Malformed or non-conforming responses are rejected with ModelInvalidResponseError.
        Invalid outputs are NEVER silently replaced with arbitrary defaults.
        """
        if cancellation_token:
            cancellation_token.check_cancelled()

        if self.budget_tracker:
            self.budget_tracker.check_pre_call()

        req_timeout = timeout or self.default_timeout

        async def _call() -> tuple[T, ModelResponse]:
            if cancellation_token:
                cancellation_token.check_cancelled()
            return await self._execute_generate_structured(
                prompt=prompt,
                response_schema=response_schema,
                system_prompt=system_prompt,
                temperature=temperature,
                timeout=req_timeout,
            )

        parsed, response = cast(
            tuple[T, ModelResponse],
            await self._retry_with_backoff(_call, cancellation_token=cancellation_token),
        )

        if self.budget_tracker:
            response_bytes = len(response.content.encode("utf-8"))
            self.budget_tracker.record_usage(response.usage, response_bytes=response_bytes)

        return parsed, response

    async def _retry_with_backoff(
        self,
        coro_fn: Any,
        cancellation_token: CancellationToken | None = None,
    ) -> Any:
        """Execute callable with exponential backoff for transient errors."""
        retries = 0
        backoff = 1.0

        while True:
            if cancellation_token:
                cancellation_token.check_cancelled()

            try:
                return await coro_fn()
            except asyncio.CancelledError as exc:
                raise ModelCancelledError("Operation cancelled during execution") from exc
            except (ModelRateLimitError, ModelServiceUnavailableError, ModelTimeoutError) as exc:
                retries += 1
                if retries > self.max_retries:
                    logger.warning(
                        "Max retries (%d) exhausted for provider %s: %s",
                        self.max_retries,
                        self.provider_name,
                        sanitize_secrets(str(exc)),
                    )
                    raise

                # Check if retry_after header was provided
                delay = getattr(exc, "retry_after_seconds", None)
                if delay is None or delay <= 0:
                    delay = backoff + random.uniform(0.1, 0.5)
                    backoff *= 2.0

                logger.info(
                    "Transient model error in %s (attempt %d/%d). Retrying in %.2fs: %s",
                    self.provider_name,
                    retries,
                    self.max_retries,
                    delay,
                    sanitize_secrets(str(exc)),
                )
                await asyncio.sleep(delay)
            except ModelError:
                # Non-retryable model error (auth, budget, schema validation)
                raise
            except ValidationError as exc:
                raise ModelInvalidResponseError(
                    f"Model output failed schema validation: {exc}",
                    provider=self.provider_name,
                    model=self.model_name,
                ) from exc
            except Exception as exc:
                # Unexpected failure, convert to normalized ModelError
                sanitized_msg = sanitize_secrets(str(exc))
                raise ModelError(
                    f"Unexpected provider error: {sanitized_msg}",
                    provider=self.provider_name,
                    model=self.model_name,
                ) from exc

    def _parse_and_validate_json(
        self,
        raw_text: str,
        schema: type[T],
    ) -> T:
        """Parse raw text as JSON and validate strictly against the Pydantic schema.

        Raises ModelInvalidResponseError if malformed or schema invalid.
        """
        clean_text = raw_text.strip()
        # Handle markdown JSON fence wrapping (e.g. ```json ... ```)
        if clean_text.startswith("```"):
            lines = clean_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_text = "\n".join(lines).strip()

        try:
            parsed_data = json.loads(clean_text)
        except json.JSONDecodeError as exc:
            raise ModelInvalidResponseError(
                f"Failed to decode model JSON output: {exc.msg} at line {exc.lineno}",
                provider=self.provider_name,
                model=self.model_name,
                details={"raw_text": raw_text[:500]},
            ) from exc

        if not isinstance(parsed_data, dict):
            raise ModelInvalidResponseError(
                f"Expected JSON object, got {type(parsed_data).__name__}",
                provider=self.provider_name,
                model=self.model_name,
            )

        try:
            return schema.model_validate(parsed_data)
        except ValidationError as exc:
            raise ModelInvalidResponseError(
                f"Model response failed schema validation for {schema.__name__}: {exc.errors()}",
                provider=self.provider_name,
                model=self.model_name,
                details={"errors": exc.errors()},
            ) from exc
