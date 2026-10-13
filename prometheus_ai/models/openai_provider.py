"""OpenAI and OpenAI-Compatible Model Provider Adapter (Official SDK).

Implements BaseModelProvider using the official OpenAI Python SDK (AsyncOpenAI).
Supports:
- Cloud OpenAI models (GPT-4o, GPT-4o-mini)
- Local inference backends (Ollama, vLLM, llama.cpp) via base_url configuration
- Native Structured Outputs and Tool Calling
- Token accounting and error normalization
"""

import json
from typing import Any, TypeVar

import openai
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


class OpenAIProvider(BaseModelProvider):
    """Adapter for OpenAI and OpenAI-compatible local endpoints."""

    def __init__(
        self,
        model_name: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        provider_name: str = "openai",
        default_timeout: float = 60.0,
        max_retries: int = 3,
        budget_tracker: BudgetTracker | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            provider_name=provider_name,
            default_timeout=default_timeout,
            max_retries=max_retries,
            budget_tracker=budget_tracker,
        )
        self.api_key = api_key
        self.base_url = base_url

        # For local endpoints (e.g. Ollama), api_key may not be strictly required by server,
        # but the OpenAI client constructor requires a non-empty string.
        client_key = api_key or "local-token-not-required"
        self.client = openai.AsyncOpenAI(
            api_key=client_key,
            base_url=base_url,
            timeout=default_timeout,
        )

    def _convert_tools_to_openai(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize tool descriptors to OpenAI function calling format."""
        openai_tools: list[dict[str, Any]] = []
        for tool in tools:
            name = tool.get("name", "")
            description = tool.get("description", "")
            schema = (
                tool.get("parameters_schema")
                or tool.get("parameters")
                or tool.get("input_schema")
                or {"type": "object", "properties": {}}
            )
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": schema,
                    },
                }
            )
        return openai_tools

    def _extract_usage(self, response: Any) -> ModelUsage:
        """Extract tokens and calculate estimated cost."""
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)

        return ModelUsage.from_counts(
            model=self.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            details={"provider": self.provider_name},
        )

    def _normalize_error(self, exc: Exception) -> ModelError:
        """Map OpenAI SDK exceptions to normalized ModelError types."""
        raw_msg = str(exc)
        safe_msg = sanitize_secrets(raw_msg, custom_secrets=[self.api_key or ""])

        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return ModelAuthenticationError(
                safe_msg, provider=self.provider_name, model=self.model_name
            )
        if isinstance(exc, openai.RateLimitError):
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
        if isinstance(exc, openai.APITimeoutError):
            return ModelTimeoutError(safe_msg, provider=self.provider_name, model=self.model_name)
        if isinstance(exc, (openai.APIConnectionError, openai.InternalServerError)):
            return ModelServiceUnavailableError(
                safe_msg, provider=self.provider_name, model=self.model_name
            )
        if isinstance(exc, openai.BadRequestError):
            if (
                "maximum context length" in safe_msg.lower()
                or "too many tokens" in safe_msg.lower()
            ):
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
        messages: list[Any] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        req_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "timeout": timeout or self.default_timeout,
        }
        if tools:
            req_kwargs["tools"] = self._convert_tools_to_openai(tools)

        try:
            raw_resp = await self.client.chat.completions.create(**req_kwargs)
        except Exception as exc:
            raise self._normalize_error(exc) from exc

        choice = raw_resp.choices[0]
        content = choice.message.content or ""
        finish_reason = choice.finish_reason

        # Parse tool calls
        tool_calls: list[ToolCallRequest] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                fn_args = {}
                if tc.function.arguments:
                    try:
                        fn_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {"raw_arguments": tc.function.arguments}
                tool_calls.append(
                    ToolCallRequest(
                        call_id=tc.id,
                        name=tc.function.name,
                        arguments=fn_args,
                    )
                )

        usage = self._extract_usage(raw_resp)

        return ModelResponse(
            content=content,
            model=self.model_name,
            provider=self.provider_name,
            usage=usage,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=finish_reason,
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
        messages: list[Any] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Try native beta structured parsing first (available on OpenAI models)
        try:
            parsed_completion = await self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=messages,
                response_format=response_schema,
                temperature=temperature,
                timeout=timeout or self.default_timeout,
            )
            choice = parsed_completion.choices[0]
            parsed_data = choice.message.parsed
            if parsed_data is not None:
                usage = self._extract_usage(parsed_completion)
                resp = ModelResponse(
                    content=parsed_data.model_dump_json(),
                    model=self.model_name,
                    provider=self.provider_name,
                    usage=usage,
                    finish_reason=choice.finish_reason,
                    is_mock=False,
                )
                return parsed_data, resp
        except (openai.BadRequestError, AttributeError, Exception):
            # Beta parse may not be supported by local endpoints (Ollama/vLLM)
            pass

        # Fallback for local endpoints or standard completions: JSON schema prompt enforcement
        system_guidance = (
            f"You MUST return valid JSON adhering strictly to this schema: "
            f"{json.dumps(response_schema.model_json_schema())}."
        )
        messages_json: list[Any] = []
        if system_prompt:
            messages_json.append(
                {"role": "system", "content": f"{system_prompt}\n\n{system_guidance}"}
            )
        else:
            messages_json.append({"role": "system", "content": system_guidance})
        messages_json.append({"role": "user", "content": prompt})

        try:
            raw_resp = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages_json,
                temperature=temperature,
                response_format={"type": "json_object"},
                timeout=timeout or self.default_timeout,
            )
        except Exception as exc:
            raise self._normalize_error(exc) from exc

        raw_choice = raw_resp.choices[0]
        content = raw_choice.message.content or ""
        usage = self._extract_usage(raw_resp)

        parsed = self._parse_and_validate_json(content, response_schema)
        resp = ModelResponse(
            content=content,
            model=self.model_name,
            provider=self.provider_name,
            usage=usage,
            finish_reason=raw_choice.finish_reason,
            is_mock=False,
        )
        return parsed, resp
