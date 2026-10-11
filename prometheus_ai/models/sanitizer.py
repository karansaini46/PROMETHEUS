"""Security Sanitizer for LLM Logs and Error Messages.

Ensures API keys, authentication tokens, and sensitive secrets are never logged
or leaked in error messages or responses.
"""

import re
from typing import Any

# Regex patterns matching API keys and tokens across common providers
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"Bearer\s+([a-zA-Z0-9_\-\.]{10,})", re.IGNORECASE),
    re.compile(
        r"(api[_-]?key|auth[_-]?token|secret[_-]?key)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{8,})['\"]?",
        re.IGNORECASE,
    ),
]


def sanitize_secrets(text: str, custom_secrets: list[str] | None = None) -> str:
    """Scrub known and detected secrets from the given text string.

    Args:
        text: Input string that may contain sensitive tokens.
        custom_secrets: Explicit secret strings (e.g., loaded API keys) to redact.

    Returns:
        Sanitized text with secrets replaced with '[REDACTED]'.
    """
    if not text:
        return text

    sanitized = text

    # Redact explicit custom secrets first if provided
    if custom_secrets:
        for secret in custom_secrets:
            if secret and len(secret) >= 4:
                sanitized = sanitized.replace(secret, "[REDACTED_SECRET]")

    # Redact known secret regex patterns
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_CREDENTIAL]", sanitized)

    return sanitized


def sanitize_dict(data: dict[str, Any], custom_secrets: list[str] | None = None) -> dict[str, Any]:
    """Recursively sanitize string values in a dictionary."""
    sanitized_data: dict[str, Any] = {}
    sensitive_keys = {"api_key", "auth_token", "secret", "password", "authorization", "x-api-key"}

    for k, v in data.items():
        if k.lower() in sensitive_keys:
            sanitized_data[k] = "[REDACTED]"
        elif isinstance(v, str):
            sanitized_data[k] = sanitize_secrets(v, custom_secrets)
        elif isinstance(v, dict):
            sanitized_data[k] = sanitize_dict(v, custom_secrets)
        elif isinstance(v, list):
            sanitized_data[k] = [
                sanitize_dict(item, custom_secrets)
                if isinstance(item, dict)
                else sanitize_secrets(item, custom_secrets)
                if isinstance(item, str)
                else item
                for item in v
            ]
        else:
            sanitized_data[k] = v

    return sanitized_data
