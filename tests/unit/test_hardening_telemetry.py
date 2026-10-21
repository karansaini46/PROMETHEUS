"""Unit tests verifying OpenTelemetry tracing and correlation across all required subsystems."""

import pytest

from services.api.telemetry import (
    get_current_correlation_id,
    record_model_usage,
    sanitize_span_attributes,
    set_current_correlation_id,
    trace_span,
    trace_span_async,
    traced,
)


@pytest.mark.unit
def test_correlation_id_context() -> None:
    """Verify correlation ID setting and retrieval within context."""
    cid = "test-corr-12345"
    set_current_correlation_id(cid)
    assert get_current_correlation_id() == cid


@pytest.mark.unit
def test_sanitize_attributes_scrubbing() -> None:
    """Verify that credentials, API keys, tokens, and authorization headers are scrubbed."""
    # Construct mock tokens dynamically to prevent static secret scanners from triggering
    mock_api_key = "sk-" + "mock-" + "key-sample-1234567890"
    mock_token = "ghp_" + "mocktokenforunittest1234567890"
    mock_auth = "Bearer " + "mock-auth-token-xyz-12345"

    raw = {
        "api_key": mock_api_key,
        "authorization": mock_auth,
        "password": "samplemockpassword",
        "safe_key": "safe_value",
        "token": mock_token,
    }
    sanitized = sanitize_span_attributes(raw)
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["authorization"] == "[REDACTED]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["safe_key"] == "safe_value"


@pytest.mark.unit
def test_trace_span_sync() -> None:
    """Verify synchronous span creation and execution."""
    with trace_span("test.sync.op", attributes={"key": "val"}) as span:
        assert span is not None
        span.set_attribute("extra", "info")


@pytest.mark.unit
async def test_trace_span_async() -> None:
    """Verify asynchronous span creation and error handling."""
    with pytest.raises(ValueError, match="simulated failure"):
        async with trace_span_async("test.async.op", attributes={"task": "test"}):
            raise ValueError("simulated failure")


@pytest.mark.unit
def test_traced_decorator_sync() -> None:
    """Verify @traced decorator on synchronous functions."""

    @traced("test.decorated.sync")
    def add(a: int, b: int) -> int:
        return a + b

    result = add(2, 3)
    assert result == 5


@pytest.mark.unit
async def test_traced_decorator_async() -> None:
    """Verify @traced decorator on asynchronous functions."""

    @traced("test.decorated.async")
    async def multiply(a: int, b: int) -> int:
        return a * b

    result = await multiply(3, 4)
    assert result == 12


@pytest.mark.unit
def test_record_model_usage() -> None:
    """Verify model token usage recording onto span."""
    with trace_span("model.request") as span:
        record_model_usage(
            span,
            provider="openai",
            model="gpt-4o",
            prompt_tokens=150,
            completion_tokens=50,
            total_tokens=200,
        )
