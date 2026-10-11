"""Anthropic Model Provider Adapter (Official SDK).

Implements BaseModelProvider using the official Anthropic Python SDK (AsyncAnthropic).
Normalizes errors, supports native tool calling, structured outputs via tool choice,
and token accounting.
"""

from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

from prometheus_ai.models.budget import BudgetTracker
from prometheus_ai.models.exceptions import (
    ModelAuthenticationError,
    ModelContextLengthError,
    ModelError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelServiceUnavailableError,
    ModelTimeoutError,
)
from prometheus_ai.models.provider import BaseModelProvider
from prometheus_ai.models.sanitizer import sanitize_secrets
from prometheus_ai.models.types import ModelResponse, ModelUsage, ToolCallRequest

T = TypeVar("T", bound=BaseModel)


class AnthropicProvider(BaseModelProvider):
    """Adapter for Anthropic Claude models via official SDK."""

    def __init__(
        self,
        model_name: str = "claude-3-5-sonnet-20241022",
        api_key: str | None = None,
        auth_token: str | None = None,
        base_url: str | None = None,
        default_timeout: float = 60.0,
        max_retries: int = 3,
        budget_tracker: BudgetTracker | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            provider_name="anthropic",
            default_timeout=default_timeout,
            max_retries=max_retries,
            budget_tracker=budget_tracker,
        )
        self.api_key = api_key
        self.auth_token = auth_token
        self.base_url = base_url

        # Initialize official AsyncAnthropic client safely
        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        elif auth_token:
            client_kwargs["auth_token"] = auth_token
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = anthropic.AsyncAnthropic(**client_kwargs)

    def _convert_tools_to_anthropic(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize tool descriptors to Anthropic format."""
        anthropic_tools: list[dict[str, Any]] = []
        for tool in tools:
            name = tool.get("name", "")
            description = tool.get("description", "")
            schema = (
                tool.get("parameters_schema")
                or tool.get("parameters")
                or tool.get("input_schema")
                or {"type": "object", "properties": {}}
            )
            anthropic_tools.append(
                {
                    "name": name,
                    "description": description,
                    "input_schema": schema,
                }
            )
        return anthropic_tools

    def _extract_usage(self, response: anthropic.types.Message) -> ModelUsage:
        """Extract tokens and calculate estimated cost."""
        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0

        return ModelUsage.from_counts(
            model=self.model_name,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cache_read=cache_read,
            cache_write=cache_write,
            details={"provider": "anthropic", "message_id": response.id},
        )

    def _normalize_error(self, exc: Exception) -> ModelError:
        """Map Anthropic SDK exceptions to normalized ModelError types."""
        raw_msg = str(exc)
        # Redact any sensitive credentials from the error text
        safe_msg = sanitize_secrets(
            raw_msg, custom_secrets=[self.api_key or "", self.auth_token or ""]
        )

        if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
            return ModelAuthenticationError(
                safe_msg, provider=self.provider_name, model=self.model_name
            )
        if isinstance(exc, anthropic.RateLimitError):
            retry_after = None
            if hasattr(exc, "response") and exc.response is not None:
                retry_header = exc.response.headers.get("retry-after")
                if retry_header:
                    try:
                        retry_after = float(retry_header)
                    except ValueError:
                        pass
            return ModelRateLimitError(
                safe_msg,
                provider=self.provider_name,
                model=self.model_name,
                retry_after_seconds=retry_after,
            )
        if isinstance(exc, anthropic.APITimeoutError):
            return ModelTimeoutError(safe_msg, provider=self.provider_name, model=self.model_name)
        if isinstance(exc, (anthropic.APIConnectionError, anthropic.InternalServerError)):
            return ModelServiceUnavailableError(
                safe_msg, provider=self.provider_name, model=self.model_name
            )
        if isinstance(exc, anthropic.BadRequestError):
            if "prompt is too long" in safe_msg.lower() or "maximum context" in safe_msg.lower():
                return ModelContextLengthError(
                    safe_msg, provider=self.provider_name, model=self.model_name
                )
            return ModelInvalidResponseError(
                safe_msg, provider=self.provider_name, model=self.model_name
            )

        return ModelError(safe_msg, provider=self.provider_name, model=self.model_name)

    async def _execute_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        timeout: float | None = None,
    ) -> ModelResponse:
        req_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
            "timeout": timeout or self.default_timeout,
        }
        if temperature > 0.0:
            req_kwargs["extra_body"] = {"temperature": temperature}
        if system_prompt:
            req_kwargs["system"] = system_prompt

        if tools:
            req_kwargs["tools"] = self._convert_tools_to_anthropic(tools)

        try:
            raw_resp = await self.client.messages.create(**req_kwargs)
        except Exception as exc:
            raise self._normalize_error(exc) from exc

        # Parse response content and tool calls
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []

        for block in raw_resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        call_id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        full_text = "\n".join(text_parts)
        usage = self._extract_usage(raw_resp)

        return ModelResponse(
            content=full_text,
            model=self.model_name,
            provider=self.provider_name,
            usage=usage,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=raw_resp.stop_reason,
            is_mock=False,
        )

    async def _execute_generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        timeout: float | None = None,
    ) -> tuple[T, ModelResponse]:
        schema_json = response_schema.model_json_schema()
        tool_name = f"submit_{response_schema.__name__.lower()}"
        tool_def = {
            "name": tool_name,
            "description": f"Submit structured output conforming to {response_schema.__name__}",
            "input_schema": schema_json,
        }

        req_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [tool_def],
            "tool_choice": {"type": "tool", "name": tool_name},
            "timeout": timeout or self.default_timeout,
        }
        if temperature > 0.0:
            req_kwargs["extra_body"] = {"temperature": temperature}
        if system_prompt:
            req_kwargs["system"] = system_prompt

        try:
            raw_resp = await self.client.messages.create(**req_kwargs)
        except Exception as exc:
            raise self._normalize_error(exc) from exc

        # Extract structured tool output
        extracted_data: dict[str, Any] | None = None
        raw_text_fallback: str = ""

        for block in raw_resp.content:
            if block.type == "tool_use" and block.name == tool_name:
                if isinstance(block.input, dict):
                    extracted_data = block.input
            elif block.type == "text":
                raw_text_fallback += block.text

        usage = self._extract_usage(raw_resp)

        if extracted_data is not None:
            try:
                parsed = response_schema.model_validate(extracted_data)
                resp = ModelResponse(
                    content=parsed.model_dump_json(),
                    model=self.model_name,
                    provider=self.provider_name,
                    usage=usage,
                    finish_reason=raw_resp.stop_reason,
                    is_mock=False,
                )
                return parsed, resp
            except Exception as exc:
                raise ModelInvalidResponseError(
                    f"Structured output from Anthropic tool failed schema validation: {exc}",
                    provider=self.provider_name,
                    model=self.model_name,
                    details={"extracted_data": extracted_data},
                ) from exc

        # Fallback to parsing text content if tool call was somehow omitted
        if raw_text_fallback:
            parsed = self._parse_and_validate_json(raw_text_fallback, response_schema)
            resp = ModelResponse(
                content=raw_text_fallback,
                model=self.model_name,
                provider=self.provider_name,
                usage=usage,
                finish_reason=raw_resp.stop_reason,
                is_mock=False,
            )
            return parsed, resp

        raise ModelInvalidResponseError(
            f"Anthropic returned no structured tool output or text matching schema {response_schema.__name__}",
            provider=self.provider_name,
            model=self.model_name,
        )
