"""Security tests verifying administrative isolation, approval checks, safe git refs, path guards, rate limits, and sanitization."""

from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from prometheus_ai.execution.guards import (
    SecurityException,
    validate_safe_git_ref,
    validate_safe_repo_dir,
)
from services.api.config import Settings
from services.api.middleware import RateLimitMiddleware
from services.api.security import (
    AuthenticatedClient,
    sanitize_message_for_client,
    verify_action_approval,
    verify_admin_access,
)


@pytest.mark.security
def test_validate_safe_git_ref() -> None:
    """Verify safe git references are permitted and malicious option flags/injections are rejected."""
    # Permitted valid refs
    assert validate_safe_git_ref("main") == "main"
    assert validate_safe_git_ref("v1.0.0") == "v1.0.0"
    assert validate_safe_git_ref("feature/branch-123") == "feature/branch-123"
    assert validate_safe_git_ref("HEAD~1") == "HEAD~1"
    assert validate_safe_git_ref("abc123def456") == "abc123def456"

    # Malicious injection: option flags starting with dash
    with pytest.raises(SecurityException, match="Git ref cannot start with a dash"):
        validate_safe_git_ref("--upload-pack=touch /tmp/pwned")

    with pytest.raises(SecurityException, match="Git ref cannot start with a dash"):
        validate_safe_git_ref("-o")

    # Malicious injection: shell control characters and command separators
    with pytest.raises(SecurityException):
        validate_safe_git_ref("main; rm -rf /")

    with pytest.raises(SecurityException):
        validate_safe_git_ref("main && curl attacker.com")

    with pytest.raises(SecurityException):
        validate_safe_git_ref("`whoami`")

    with pytest.raises(SecurityException):
        validate_safe_git_ref("$(reboot)")

    with pytest.raises(SecurityException):
        validate_safe_git_ref("ref\x00nullbyte")


@pytest.mark.security
def test_validate_safe_repo_dir(tmp_path: Path) -> None:
    """Verify repository path validation restricts access to safe directories and blocks OS critical paths."""
    # Safe directory under tmp_path
    safe_dir = tmp_path / "my_project"
    safe_dir.mkdir()
    resolved = validate_safe_repo_dir(str(safe_dir))
    assert resolved == safe_dir.resolve()

    # Blocked system directories
    with pytest.raises(SecurityException, match="Access denied"):
        validate_safe_repo_dir("/etc")

    with pytest.raises(SecurityException, match="Access denied"):
        validate_safe_repo_dir("/proc")

    with pytest.raises(SecurityException, match="Access denied"):
        validate_safe_repo_dir("/sys")

    with pytest.raises(SecurityException, match="Access denied"):
        validate_safe_repo_dir("/")


@pytest.mark.security
def test_verify_admin_access_enforcement() -> None:
    """Verify administrative separation: users are forbidden, admins are allowed."""
    user_client = AuthenticatedClient(client_id="user-1", is_authenticated=True, role="user")
    admin_client = AuthenticatedClient(client_id="admin-1", is_authenticated=True, role="admin")

    # User client must be rejected with 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        verify_admin_access(user_client)
    assert exc_info.value.status_code == 403
    assert "Administrative privileges required" in exc_info.value.detail

    # Admin client succeeds
    verified = verify_admin_access(admin_client)
    assert verified.is_admin is True


@pytest.mark.security
def test_verify_action_approval_enforcement() -> None:
    """Verify explicit human approval requirement in production environments."""
    prod_settings = Settings(
        PROMETHEUS_ENV="production",
        REQUIRE_AUTH=True,
        REQUIRE_APPROVAL_FOR_DESTRUCTIVE=True,
    )

    # Missing approval header in production -> 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        verify_action_approval(
            x_approval_confirmed=None,
            settings=prod_settings,
        )
    assert exc_info.value.status_code == 403
    assert "requires explicit human approval" in exc_info.value.detail

    # Provided approval header -> allowed
    approved = verify_action_approval(
        x_approval_confirmed="approved",
        settings=prod_settings,
    )
    assert approved is True


@pytest.mark.security
async def test_rate_limit_middleware_enforcement() -> None:
    """Verify sliding window rate limiting returns 429 Too Many Requests when threshold exceeded."""

    async def dummy_app(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"status": "ok"})
        await response(scope, receive, send)

    # Middleware allowing max 2 requests per minute
    middleware = RateLimitMiddleware(dummy_app, max_requests_per_minute=2)

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/test",
        "client": ("192.168.1.100", 54321),
        "headers": [],
    }

    async def receive() -> Message:
        return {"type": "http.request"}

    # Request 1: allowed
    msgs1: list[Message] = []

    async def send1(m: Message) -> None:
        msgs1.append(m)

    await middleware(scope, receive, send1)
    start1 = next(m for m in msgs1 if m["type"] == "http.response.start")
    assert start1["status"] == 200

    # Request 2: allowed
    msgs2: list[Message] = []

    async def send2(m: Message) -> None:
        msgs2.append(m)

    await middleware(scope, receive, send2)
    start2 = next(m for m in msgs2 if m["type"] == "http.response.start")
    assert start2["status"] == 200

    # Request 3: rate limited (429)
    msgs3: list[Message] = []

    async def send3(m: Message) -> None:
        msgs3.append(m)

    await middleware(scope, receive, send3)
    start3 = next(m for m in msgs3 if m["type"] == "http.response.start")
    assert start3["status"] == 429


@pytest.mark.security
def test_sanitize_message_for_client() -> None:
    """Verify sensitive filesystem paths and API keys are redacted from user-facing error messages."""
    mock_ant_token = "sk-" + "ant-" + "api03-samplemockkey1234567890abcdef"
    mock_gh_token = "ghp_" + "samplemocktoken1234567890abcdef"
    raw_message = (
        f"Internal error executing /home/karan/Desktop/PROMETHEUS/secrets/key.txt "
        f"with token {mock_ant_token} and {mock_gh_token}"
    )
    sanitized = sanitize_message_for_client(raw_message)
    assert "/home/karan/Desktop/PROMETHEUS" not in sanitized
    assert "sk-ant" not in sanitized
    assert "samplemocktoken" not in sanitized
    assert "[REDACTED_PATH]" in sanitized
    assert "[REDACTED_KEY]" in sanitized
