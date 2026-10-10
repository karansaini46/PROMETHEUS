"""Unit tests for API input validation, mass assignment prevention, and correlation IDs."""

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_correlation_id_propagated_in_response(async_client: AsyncClient) -> None:
    """Ensure X-Correlation-ID is included in all response headers."""
    res = await async_client.get("/api/v1/health")
    assert res.status_code == 200
    assert "X-Correlation-ID" in res.headers
    assert res.headers["X-Correlation-ID"].startswith("corr-")


@pytest.mark.unit
async def test_custom_correlation_id_retained(async_client: AsyncClient) -> None:
    """Ensure client-supplied X-Correlation-ID is preserved."""
    headers = {"X-Correlation-ID": "custom-trace-9999"}
    res = await async_client.get("/api/v1/health", headers=headers)
    assert res.status_code == 200
    assert res.headers["X-Correlation-ID"] == "custom-trace-9999"


@pytest.mark.unit
async def test_mass_assignment_prevented_in_task_creation(
    async_client: AsyncClient,
) -> None:
    """Payload with forbidden extra fields must be rejected by Pydantic extra='forbid'."""
    payload = {
        "project_id": "proj-101",
        "title": "Valid Title Here",
        "problem_statement": "Valid description statement",
        "isAdmin": True,  # Forbidden unknown property
        "role": "superuser",
    }
    res = await async_client.post("/api/v1/tasks", json=payload)
    assert res.status_code == 422
    data = res.json()
    assert data["error"] == "ValidationError"
    assert "correlation_id" in data


@pytest.mark.unit
async def test_invalid_task_type_enum_rejected(async_client: AsyncClient) -> None:
    """Invalid enum values must fail schema validation."""
    payload = {
        "project_id": "proj-101",
        "title": "Valid Title",
        "problem_statement": "Valid problem description",
        "task_type": "NOT_A_REAL_TYPE",
    }
    res = await async_client.post("/api/v1/tasks", json=payload)
    assert res.status_code == 422


@pytest.mark.unit
async def test_short_title_rejected(async_client: AsyncClient) -> None:
    """Titles shorter than min_length=3 must be rejected."""
    payload = {
        "project_id": "proj-101",
        "title": "ab",
        "problem_statement": "Valid problem description",
    }
    res = await async_client.post("/api/v1/tasks", json=payload)
    assert res.status_code == 422
