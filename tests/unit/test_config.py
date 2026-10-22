"""Unit tests for configuration validation."""

import pytest
from pydantic import ValidationError

from services.api.config import Settings


@pytest.mark.unit
def test_default_settings_valid() -> None:
    """Verify that default settings instantiate without error."""
    settings = Settings()
    assert settings.PROMETHEUS_ENV in ["development", "test", "production"]
    assert settings.API_PORT in [8000, 8001]
    assert settings.SANDBOX_PIDS_LIMIT == 256
    assert settings.DATABASE_POOL_SIZE > 0


@pytest.mark.unit
def test_short_secret_key_rejected() -> None:
    """Verify that an insecure short secret key is rejected by the validator."""
    with pytest.raises(ValidationError):
        Settings(API_SECRET_KEY="too-short")


@pytest.mark.unit
def test_invalid_pids_limit_rejected() -> None:
    """Verify that unsafe PID limits (<16 or >2048) raise validation error."""
    with pytest.raises(ValidationError):
        Settings(SANDBOX_PIDS_LIMIT=5)

    with pytest.raises(ValidationError):
        Settings(SANDBOX_PIDS_LIMIT=50000)


@pytest.mark.unit
def test_production_rejects_default_secrets() -> None:
    """Verify that production rejects default dev secrets and unauthenticated mode."""
    # Rejects default dev secret key
    with pytest.raises(ValidationError, match="API_SECRET_KEY cannot use the default"):
        Settings(
            PROMETHEUS_ENV="production",
            API_SECRET_KEY="dev-secret-key-replace-with-secure-value-in-production-min-32-chars",
            ADMIN_SECRET_KEY="a-secure-production-admin-key-at-least-32-chars",
            REQUIRE_AUTH=True,
        )

    # Rejects default dev admin key
    with pytest.raises(ValidationError, match="ADMIN_SECRET_KEY cannot use the default"):
        Settings(
            PROMETHEUS_ENV="production",
            API_SECRET_KEY="a-secure-production-api-key-at-least-32-chars",
            ADMIN_SECRET_KEY="dev-admin-secret-key-replace-with-secure-value-min-32-chars",
            REQUIRE_AUTH=True,
        )

    # Rejects REQUIRE_AUTH=False in production
    with pytest.raises(ValidationError, match="REQUIRE_AUTH must be set to True"):
        Settings(
            PROMETHEUS_ENV="production",
            API_SECRET_KEY="a-secure-production-api-key-at-least-32-chars",
            ADMIN_SECRET_KEY="a-secure-production-admin-key-at-least-32-chars",
            REQUIRE_AUTH=False,
        )

    # Valid production settings pass
    prod_settings = Settings(
        PROMETHEUS_ENV="production",
        API_SECRET_KEY="a-secure-production-api-key-at-least-32-chars",
        ADMIN_SECRET_KEY="a-secure-production-admin-key-at-least-32-chars",
        REQUIRE_AUTH=True,
    )
    assert prod_settings.PROMETHEUS_ENV == "production"
    assert prod_settings.REQUIRE_AUTH is True
