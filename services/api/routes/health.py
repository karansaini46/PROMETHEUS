"""Health and readiness system status check endpoints."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

import docker
from services.api.config import get_settings
from services.api.db import check_db_health
from services.api.worker import WorkerManager

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
    worker: dict[str, Any] | None = None


class ReadinessResponse(BaseModel):
    """System readiness check model."""

    ready: bool
    database: str
    worker_healthy: bool
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
    worker_metrics = WorkerManager.get_instance().get_health_metrics()

    worker_ok = worker_metrics.get("healthy", False)
    overall_status = "healthy" if (db_ok and worker_ok) else "degraded"

    return HealthResponse(
        status=overall_status,
        version="0.1.0",
        environment=settings.PROMETHEUS_ENV,
        timestamp=datetime.now(UTC).isoformat(),
        database="connected" if db_ok else "disconnected",
        sandbox_available=sandbox_ok,
        worker=worker_metrics,
    )


@router.get("/health/worker")
async def get_worker_health() -> dict[str, Any]:
    """Return dedicated worker supervisor and heartbeat health status."""
    return WorkerManager.get_instance().get_health_metrics()


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
    worker_metrics = WorkerManager.get_instance().get_health_metrics()
    worker_healthy = worker_metrics.get("healthy", False)
    now_str = datetime.now(UTC).isoformat()

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            ready=False,
            database="disconnected",
            worker_healthy=worker_healthy,
            timestamp=now_str,
        )

    return ReadinessResponse(
        ready=True,
        database="connected",
        worker_healthy=worker_healthy,
        timestamp=now_str,
    )
