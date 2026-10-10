"""Unit tests for runs management endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_create_and_fetch_run(async_client: AsyncClient) -> None:
    """Test creating a run and verifying its initial pending state."""
    payload = {
        "issue_id": "test-issue-101",
        "model_provider": "anthropic/claude-3-5-sonnet-20241022",
    }
    response = await async_client.post("/api/v1/runs", json=payload)
    assert response.status_code == 201

    created_run = response.json()
    assert created_run["issue_id"] == "test-issue-101"
    assert created_run["status"] == "PENDING"
    assert created_run["iteration_count"] == 0
    assert "id" in created_run

    run_id = created_run["id"]

    # Fetch the run by ID
    get_res = await async_client.get(f"/api/v1/runs/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == run_id

    # List runs includes the newly created run
    list_res = await async_client.get("/api/v1/runs")
    assert list_res.status_code == 200
    runs = list_res.json()
    assert any(r["id"] == run_id for r in runs)
