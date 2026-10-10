"""PROMETHEUS Security, Authentication Boundaries & Input Sanitization.

Provides local-first authentication, API key validation, path disclosure
prevention, and safe error message filtering.
"""

import hmac
import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from services.api.config import Settings, get_settings


class AuthenticatedClient:
    """Represents an authorized caller (UI, CLI, or agent runtime)."""

    def __init__(self, client_id: str, is_authenticated: bool = True) -> None:
        self.client_id = client_id
        self.is_authenticated = is_authenticated


def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    settings: Annotated[Settings | None, Depends(get_settings)] = None,
) -> AuthenticatedClient:
    effective_settings = settings if settings is not None else get_settings()
    """Verify incoming client credentials against configured system secret.

    Supports both X-API-Key header and Authorization: Bearer <key>.
    In local-first mode (REQUIRE_AUTH=False), allows unauthenticated local callers,
    but strictly rejects explicitly provided invalid tokens.
    """
    token: str | None = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    expected_key = effective_settings.API_SECRET_KEY

    # If a token was provided, validate it with constant-time comparison
    if token is not None:
        if not hmac.compare_digest(token, expected_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API authentication credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthenticatedClient(client_id="authenticated-user", is_authenticated=True)

    # If auth is strictly required and no token provided
    require_auth = getattr(effective_settings, "REQUIRE_AUTH", False)
    if require_auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required API authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Local-first development default
    return AuthenticatedClient(client_id="local-user", is_authenticated=True)


def sanitize_message_for_client(msg: str) -> str:
    """Remove local filesystem paths and trace details from client-facing messages."""
    # Replace absolute UNIX paths like /home/user/... or /data/...
    cleaned = re.sub(r"/(?:[a-zA-Z0-9_-]+/)+[a-zA-Z0-9_.-]+", "[REDACTED_PATH]", msg)
    # Strip potential API key patterns (e.g. sk-..., key-...)
    cleaned = re.sub(r"(?:sk-[a-zA-Z0-9]{20,}|key-[a-zA-Z0-9]{20,})", "[REDACTED_KEY]", cleaned)
    return cleaned
