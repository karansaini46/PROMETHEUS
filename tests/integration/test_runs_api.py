"""Integration tests for execution runs API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_run_lifecycle_and_ordered_events(async_client: AsyncClient) -> None:
    """Verify run creation, stable identifier, event retrieval, and cancellation."""
    # 1. Create a task first
    task_res = await async_client.post(
        "/api/v1/tasks",
        json={
            "project_id": "proj-runs-e2e",
            "title": "Bug in query serializer",
            "problem_statement": "Query serializer drops nested filters.",
        },
    )
    assert task_res.status_code == 201
    task_id = task_res.json()["id"]

    # 2. Start an execution run
    run_payload = {
        "task_id": task_id,
        "model_provider": "anthropic/claude-3-5-sonnet-20241022",
        "configuration_snapshot": {"sandbox_timeout": 300},
    }
    create_run_res = await async_client.post("/api/v1/runs", json=run_payload)
    assert create_run_res.status_code == 201
    run_data = create_run_res.json()

    run_id = run_data["id"]
    assert run_id.startswith("run_")
    assert run_data["task_id"] == task_id
    assert run_data["status"] == "PENDING"
    assert run_data["current_step"] == "INITIALIZED"

    # 3. Retrieve run status
    status_res = await async_client.get(f"/api/v1/runs/{run_id}")
    assert status_res.status_code == 200
    assert status_res.json()["id"] == run_id

    # 4. Retrieve ordered execution events
    events_res = await async_client.get(f"/api/v1/runs/{run_id}/events")
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) >= 2  # INITIALIZED agent step + RUN_STARTED audit event
    assert events[0]["sequence"] == 1
    assert "timestamp" in events[0]
    assert "event_type" in events[0]

    # 5. Cancel the run
    cancel_res = await async_client.post(f"/api/v1/runs/{run_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"
    assert cancel_res.json()["completed_at"] is not None

    # 6. Attempting to cancel an already cancelled run must fail with 409 Conflict
    re_cancel_res = await async_client.post(f"/api/v1/runs/{run_id}/cancel")
    assert re_cancel_res.status_code == 409
    error_data = re_cancel_res.json()
    assert error_data["error"] == "InvalidStateTransition"
    assert error_data["current_status"] == "CANCELLED"
    assert error_data["target_status"] == "CANCELLED"
