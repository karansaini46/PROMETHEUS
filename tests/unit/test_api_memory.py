"""Unit tests for the Memory Subsystem REST API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_memory_api_lifecycle(async_client: AsyncClient) -> None:
    """Test full CRUD, search, verification, and deletion lifecycle via REST API."""
    # 1. Create Memory
    create_payload = {
        "memory_type": "episodic",
        "key": "api_test_memory_key",
        "content": "Investigated memory leak in connection pool; fixed by setting timeout.",
        "project_id": "proj-api-1",
        "task_id": "task-api-1",
        "run_id": "run-api-1",
        "confidence": 0.85,
        "verification_status": "observed",
        "evidence": ["run_id=run-api-1"],
    }
    resp = await async_client.post("/api/v1/memory", json=create_payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    memory_id = data["id"]
    assert data["key"] == "api_test_memory_key"
    assert data["memory_type"] == "episodic"

    # 2. Inspect Memory by ID
    inspect_resp = await async_client.get(f"/api/v1/memory/{memory_id}")
    assert inspect_resp.status_code == 200
    assert inspect_resp.json()["id"] == memory_id

    # 3. Retrieve Memory with project filter
    list_resp = await async_client.get(
        "/api/v1/memory",
        params={"project_id": "proj-api-1", "query": "connection pool"},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(m["id"] == memory_id for m in items)

    # 4. Cross-project retrieval without reason must return 400
    bad_cross_resp = await async_client.get(
        "/api/v1/memory",
        params={"project_id": "proj-api-1", "include_cross_project": True},
    )
    assert bad_cross_resp.status_code == 400

    # 5. Verify Memory with evidence
    verify_resp = await async_client.post(
        f"/api/v1/memory/{memory_id}/verify",
        json={"evidence": ["integration_test_passed.log"], "verified_by_run_id": "run-ver-1"},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["verification_status"] == "verified"

    # 6. Delete Memory
    del_resp = await async_client.delete(f"/api/v1/memory/{memory_id}")
    assert del_resp.status_code == 204

    # 7. Confirm Not Found
    get_after_del = await async_client.get(f"/api/v1/memory/{memory_id}")
    assert get_after_del.status_code == 404
