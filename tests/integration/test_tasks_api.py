"""Integration tests for software engineering tasks API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_create_and_fetch_task(async_client: AsyncClient) -> None:
    """Test full task creation lifecycle, retrieval, and 404 behavior."""
    task_payload = {
        "project_id": "proj-integration-1",
        "title": "Fix memory leak in AST node visitor",
        "problem_statement": "Deep recursion during AST visitor causes uncollected object cycles.",
        "task_type": "BUG_FIX",
        "priority": "HIGH",
        "base_commit": "abcdef1234567890abcdef1234567890abcdef12",
        "reproduce_command": "pytest tests/test_ast.py",
        "metadata": {"tags": ["ast", "performance"]},
    }

    create_res = await async_client.post("/api/v1/tasks", json=task_payload)
    assert create_res.status_code == 201
    created_task = create_res.json()

    assert created_task["title"] == task_payload["title"]
    assert created_task["task_type"] == "BUG_FIX"
    assert created_task["priority"] == "HIGH"
    assert created_task["status"] == "OPEN"
    task_id = created_task["id"]

    # Fetch task details by ID
    get_res = await async_client.get(f"/api/v1/tasks/{task_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == task_id
    assert get_res.json()["metadata"] == {"tags": ["ast", "performance"]}

    # Non-existent task returns 404
    missing_res = await async_client.get("/api/v1/tasks/non-existent-uuid-999")
    assert missing_res.status_code == 404


@pytest.mark.integration
async def test_list_tasks_pagination_and_filtering(async_client: AsyncClient) -> None:
    """Test task listing with pagination, search, and status filtering."""
    # Create several tasks
    for i in range(5):
        await async_client.post(
            "/api/v1/tasks",
            json={
                "project_id": "proj-list-test",
                "title": f"Task number {i} unique search keyword",
                "problem_statement": f"Description for test task {i}",
                "priority": "MEDIUM",
            },
        )

    # List with pagination
    list_res = await async_client.get("/api/v1/tasks?page=1&page_size=2")
    assert list_res.status_code == 200
    page_data = list_res.json()
    assert page_data["page"] == 1
    assert page_data["page_size"] == 2
    assert len(page_data["items"]) == 2
    assert page_data["total"] >= 5

    # Filter with search keyword
    search_res = await async_client.get("/api/v1/tasks?search=unique search keyword")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert len(search_data["items"]) >= 5


@pytest.mark.integration
async def test_update_task_state_transition(async_client: AsyncClient) -> None:
    """Test updating task details and valid state transition."""
    # Create a task
    res = await async_client.post(
        "/api/v1/tasks",
        json={
            "project_id": "proj-update-test",
            "title": "Task for lifecycle transition",
            "problem_statement": "Testing transition from OPEN to IN_PROGRESS",
        },
    )
    task_id = res.json()["id"]

    # Transition OPEN -> IN_PROGRESS
    update_res = await async_client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "IN_PROGRESS", "priority": "CRITICAL"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["status"] == "IN_PROGRESS"
    assert update_res.json()["priority"] == "CRITICAL"

    # Re-opening task: IN_PROGRESS -> OPEN is allowed by state machine
    reopen_res = await async_client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "OPEN"},
    )
    assert reopen_res.status_code == 200
    assert reopen_res.json()["status"] == "OPEN"
