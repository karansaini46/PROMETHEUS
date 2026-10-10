"""Health and readiness system status check endpoints."""

from datetime import UTC, datetime

import docker
from fastapi import APIRouter, Response, status
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


class ReadinessResponse(BaseModel):
    """System readiness check model."""

    ready: bool
    database: str
    timestamp: str


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


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_200_OK: {"description": "System is ready to serve traffic"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "System is not ready"},
    },
)
async def get_readiness(response: Response) -> ReadinessResponse:
    """Return platform readiness probe for load balancers and orchestrators."""
    db_ok = await check_db_health()
    now_str = datetime.now(UTC).isoformat()

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            ready=False,
            database="disconnected",
            timestamp=now_str,
        )

    return ReadinessResponse(
        ready=True,
        database="connected",
        timestamp=now_str,
    )
