"""PROMETHEUS Security, Authentication Boundaries & Input Sanitization.

Provides local-first authentication, role-based access control (Admin / User),
API key validation, path disclosure prevention, explicit approval guards for
destructive operations, and safe error message filtering.
"""

import hmac
import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from services.api.config import Settings, get_settings


class AuthenticatedClient:
    """Represents an authorized caller (UI, CLI, worker, or administrative operator)."""

    def __init__(
        self,
        client_id: str,
        is_authenticated: bool = True,
        role: str = "user",
    ) -> None:
        self.client_id = client_id
        self.is_authenticated = is_authenticated
        self.role = role

    @property
    def is_admin(self) -> bool:
        """Check whether the client possesses administrative privileges."""
        return self.role == "admin"


def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
    settings: Annotated[Settings | None, Depends(get_settings)] = None,
) -> AuthenticatedClient:
    """Verify incoming client credentials against configured system secrets.

    Supports X-API-Key, Authorization: Bearer <token>, and dedicated X-Admin-Key.
    Separates administrative callers from standard callers.
    In local-first mode (REQUIRE_AUTH=False), allows unauthenticated local callers,
    but strictly rejects explicitly provided invalid tokens.
    """
    effective_settings = settings if settings is not None else get_settings()

    # 1. Check for administrative credential first
    if x_admin_key:
        admin_token = x_admin_key.strip()
        expected_admin = effective_settings.ADMIN_SECRET_KEY
        if hmac.compare_digest(admin_token, expected_admin):
            return AuthenticatedClient(
                client_id="admin-operator", is_authenticated=True, role="admin"
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrative credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Extract standard token
    token: str | None = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    expected_user = effective_settings.API_SECRET_KEY
    expected_admin = effective_settings.ADMIN_SECRET_KEY

    # If a token was provided, validate with constant-time comparison
    if token is not None:
        if hmac.compare_digest(token, expected_admin):
            return AuthenticatedClient(client_id="admin-user", is_authenticated=True, role="admin")
        if hmac.compare_digest(token, expected_user):
            return AuthenticatedClient(
                client_id="authenticated-user", is_authenticated=True, role="user"
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. If auth is strictly required and no token was provided
    if effective_settings.REQUIRE_AUTH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required API authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Local-first development default
    return AuthenticatedClient(
        client_id="local-user",
        is_authenticated=True,
        role="admin" if not effective_settings.REQUIRE_AUTH else "user",
    )


def verify_admin_access(
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> AuthenticatedClient:
    """Enforce that the caller holds administrative privileges."""
    if not client.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to perform this action.",
        )
    return client


def verify_action_approval(
    x_approval_confirmed: Annotated[str | None, Header(alias="X-Action-Approval")] = None,
    client: Annotated[AuthenticatedClient | None, Depends(verify_api_key)] = None,
    settings: Annotated[Settings | None, Depends(get_settings)] = None,
) -> bool:
    """Enforce explicit approval for destructive actions, external PRs, or deployments."""
    effective_settings = settings if settings is not None else get_settings()
    if not effective_settings.REQUIRE_APPROVAL_FOR_DESTRUCTIVE:
        return True

    # In local test/development mode with REQUIRE_AUTH=False, allow unless explicitly in production
    if not effective_settings.REQUIRE_AUTH and effective_settings.PROMETHEUS_ENV != "production":
        return True

    # Header or administrative confirmation
    if x_approval_confirmed and x_approval_confirmed.strip().lower() in (
        "true",
        "confirmed",
        "approved",
        "1",
    ):
        return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Operation requires explicit human approval. Pass 'X-Action-Approval: approved' "
            "header or approve via the control plane before executing destructive or external actions."
        ),
    )


def sanitize_message_for_client(msg: str) -> str:
    """Remove local filesystem paths, API keys, and stack details from client-facing messages."""
    # Replace absolute UNIX paths like /home/user/... or /data/...
    cleaned = re.sub(r"/(?:[a-zA-Z0-9_\.-]+/)+[a-zA-Z0-9_\.-]+", "[REDACTED_PATH]", msg)
    # Strip potential API key patterns (e.g. sk-..., key-..., ghp-...)
    cleaned = re.sub(
        r"(?:sk-[a-zA-Z0-9_\-]{15,}|key-[a-zA-Z0-9_\-]{15,}|ghp_[a-zA-Z0-9_\-]{15,}|github_pat_[a-zA-Z0-9_]{20,}|glpat-[a-zA-Z0-9_\-]{15,})",
        "[REDACTED_KEY]",
        cleaned,
    )
    return cleaned
