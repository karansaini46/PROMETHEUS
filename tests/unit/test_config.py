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
