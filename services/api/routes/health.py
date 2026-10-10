"""Health and system status check endpoint."""

from datetime import UTC, datetime

import docker
from fastapi import APIRouter
from pydantic import BaseModel

from services.api.config import get_settings
from services.api.db import check_db_health

router = APIRouter(tags=["Health"])
settings = get_settings()


class HealthResponse(BaseModel):
    """System health check model."""

    status: str
    version: str
    environment: str
    timestamp: str
    database: str
    sandbox_available: bool


def is_sandbox_available() -> bool:
    """Check if the Docker daemon is reachable for sandbox isolation."""
    try:
        client = docker.from_env(timeout=2)
        return bool(client.ping())
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Return platform subsystem health metrics."""
    db_ok = await check_db_health()
    sandbox_ok = is_sandbox_available()

    overall_status = "healthy" if db_ok else "degraded"

    return HealthResponse(
        status=overall_status,
        version="0.1.0",
        environment=settings.PROMETHEUS_ENV,
        timestamp=datetime.now(UTC).isoformat(),
        database="connected" if db_ok else "disconnected",
        sandbox_available=sandbox_ok,
    )
