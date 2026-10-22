"""Unit tests for the health check endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_health_endpoint(async_client: AsyncClient) -> None:
    """Test GET /api/v1/health returns valid structured health response."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "degraded"]
    assert "version" in data
    assert data["version"] == "0.1.0"
    assert "database" in data
    assert "sandbox_available" in data
    assert isinstance(data["sandbox_available"], bool)


@pytest.mark.unit
async def test_root_health_and_readiness_endpoints(async_client: AsyncClient) -> None:
    """Test GET /health and GET /ready at root paths."""
    health_resp = await async_client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] in ["healthy", "degraded"]

    ready_resp = await async_client.get("/ready")
    assert ready_resp.status_code in [200, 503]
    assert "ready" in ready_resp.json()

    worker_resp = await async_client.get("/health/worker")
    assert worker_resp.status_code == 200
    assert "status" in worker_resp.json()
