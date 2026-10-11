"""Security Tests for Secrets and Credential Protection in Model Invocations.

Verifies:
- API keys and tokens are never leaked in error messages
- Secrets are not included in ModelResponse or ModelUsage representations
- Sanitizer effectively redacts Anthropic and OpenAI key patterns
- Logging sanitization prevents accidental token leakage
"""

import pytest

from prometheus_ai.models.exceptions import ModelAuthenticationError
from prometheus_ai.models.sanitizer import sanitize_dict, sanitize_secrets
from prometheus_ai.models.types import ModelResponse, ModelUsage


@pytest.mark.security
def test_secrets_redacted_from_error_messages() -> None:
    """Verify that exception strings and logs do not contain raw API keys."""
    raw_secret_key = "sk-ant-api03-abcdef1234567890abcdef1234567890-test"
    error_msg = f"Failed to authenticate against provider with key {raw_secret_key}: HTTP 401"

    err = ModelAuthenticationError(error_msg, provider="anthropic", model="claude-3-5-sonnet")
    err_str = str(err)

    assert raw_secret_key not in err_str
    assert "[REDACTED" in err_str
    assert "anthropic/claude-3-5-sonnet" in err_str


@pytest.mark.security
def test_secrets_redacted_from_custom_secrets_list() -> None:
    """Verify custom secrets (e.g. dynamically configured tokens) are scrubbed."""
    custom_token = "my-super-secret-internal-org-token-998877"
    raw_text = f"Connection error: could not send authorization bearer {custom_token} to endpoint"

    sanitized = sanitize_secrets(raw_text, custom_secrets=[custom_token])
    assert custom_token not in sanitized
    assert "[REDACTED_SECRET]" in sanitized


@pytest.mark.security
def test_secrets_redacted_from_dictionary_structures() -> None:
    """Verify recursive dictionary scrubbing removes sensitive headers and parameters."""
    data = {
        "headers": {
            "x-api-key": "sk-ant-live-secret-key-12345678901234567890",
            "content-type": "application/json",
        },
        "auth_token": "secret-auth-token-value-99999",
        "nested": {
            "prompt": "Investigate bug in login code",
            "api_key": "sk-openai-live-key-99999999999999999999",
        },
    }

    sanitized = sanitize_dict(data)
    assert sanitized["headers"]["x-api-key"] == "[REDACTED]"
    assert sanitized["auth_token"] == "[REDACTED]"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["prompt"] == "Investigate bug in login code"


@pytest.mark.security
def test_model_response_and_usage_do_not_contain_secrets() -> None:
    """Verify ModelResponse and ModelUsage structures do not expose authorization tokens."""
    usage = ModelUsage(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.001,
        details={"provider": "anthropic"},
    )
    response = ModelResponse(
        content="Bug analysis completed.",
        model="claude-3-5-sonnet",
        provider="anthropic",
        usage=usage,
    )

    resp_str = repr(response)
    usage_str = repr(usage)

    assert "api_key" not in resp_str.lower()
    assert "token" not in resp_str.lower() or "tokens" in resp_str.lower()
    assert "secret" not in resp_str.lower()
    assert "secret" not in usage_str.lower()


@pytest.mark.security
def test_gemini_api_key_redacted() -> None:
    """Verify that Google Gemini API keys are redacted automatically."""
    gemini_key = "AIzaSyD1234567890abcdefghijklmnopqrst"
    error_msg = f"Failed to authenticate against Gemini with key {gemini_key}: 401 Unauthorized"
    sanitized = sanitize_secrets(error_msg)

    assert gemini_key not in sanitized
    assert "[REDACTED_CREDENTIAL]" in sanitized
