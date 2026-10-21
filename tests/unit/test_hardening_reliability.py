"""Unit tests verifying reliability mechanisms: timeouts, idempotency, worker health, crash recovery, and resource cleanup."""

import asyncio
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from prometheus_ai.execution.sandbox import CancellationToken
from prometheus_ai.tools.execution import ExecutionRegistry
from services.api.middleware import RequestTimeoutMiddleware
from services.api.models import (
    ExecutionRun,
    Project,
    RunStatusEnum,
    Task,
    TaskStatusEnum,
)
from services.api.worker import WorkerManager


@pytest.mark.unit
def test_worker_manager_singleton() -> None:
    """Verify WorkerManager instance reuse and health metrics."""
    mgr1 = WorkerManager.get_instance()
    mgr2 = WorkerManager.get_instance()
    assert mgr1 is mgr2

    metrics = mgr1.get_health_metrics()
    assert "status" in metrics
    assert "uptime_seconds" in metrics
    assert "active_tasks" in metrics
    assert "last_heartbeat" in metrics


@pytest.mark.unit
async def test_worker_health_endpoint(async_client: AsyncClient) -> None:
    """Verify /api/v1/health/worker returns worker supervisor state."""
    resp = await async_client.get("/api/v1/health/worker")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "uptime_seconds" in data
    assert "active_tasks" in data


@pytest.mark.unit
def test_execution_registry_cancellation() -> None:
    """Verify execution registry registration, tracking, and cancellation."""
    registry = ExecutionRegistry.get_instance()
    run_id = f"test-run-{uuid4().hex[:8]}"

    token = CancellationToken()
    assert token.is_cancelled is False

    registry.register(run_id, token, runner=None)

    # Cancel execution
    success = registry.cancel(run_id)
    assert success is True
    assert token.is_cancelled is True

    # Check unregister
    registry.unregister(run_id)


@pytest.mark.unit
async def test_recover_interrupted_tasks(test_db_session: AsyncSession) -> None:
    """Verify that interrupted RUNNING tasks/runs are marked as FAILED with audit events upon recovery."""
    mgr = WorkerManager.get_instance()

    # Create a parent project, stuck task, and run
    proj_id = f"proj-rec-{uuid4().hex[:6]}"
    proj = Project(
        id=proj_id,
        name="Recovery Test Project",
        slug=f"slug-rec-{uuid4().hex[:6]}",
        repository_url="https://github.com/org/test-repo",
    )
    test_db_session.add(proj)

    task_id = f"stuck-task-{uuid4().hex[:8]}"
    run_id = f"stuck-run-{uuid4().hex[:8]}"

    stuck_task = Task(
        id=task_id,
        project_id=proj_id,
        title="Stuck Task from prior crash",
        problem_statement="Investigating crash recovery failure mode",
        status=TaskStatusEnum.IN_PROGRESS,
    )
    stuck_run = ExecutionRun(
        id=run_id,
        task_id=task_id,
        model_provider="anthropic",
        status=RunStatusEnum.RUNNING,
    )

    test_db_session.add(stuck_task)
    test_db_session.add(stuck_run)
    await test_db_session.commit()

    # Run recovery with our test session
    recovered_count = await mgr.recover_interrupted_tasks(db=test_db_session)
    assert recovered_count >= 1

    # Verify task state is reset to OPEN and run is FAILED with error details
    await test_db_session.refresh(stuck_task)
    await test_db_session.refresh(stuck_run)
    assert stuck_task.status == TaskStatusEnum.OPEN
    assert stuck_run.status == RunStatusEnum.FAILED
    assert stuck_run.error_message is not None
    assert "Process terminated abruptly" in stuck_run.error_message


@pytest.mark.unit
async def test_cleanup_abandoned_resources() -> None:
    """Verify that abandoned resource cleanup runs without error."""
    mgr = WorkerManager.get_instance()
    cleaned = await mgr.cleanup_abandoned_resources()
    assert isinstance(cleaned, dict)
    assert "cleaned_worktrees" in cleaned
    assert "cleaned_containers" in cleaned


@pytest.mark.unit
async def test_request_timeout_middleware_trigger() -> None:
    """Verify RequestTimeoutMiddleware returns 504 Gateway Timeout when processing exceeds timeout."""

    async def slow_app(scope: Scope, receive: Receive, send: Send) -> None:
        await asyncio.sleep(0.2)
        response = JSONResponse({"status": "ok"})
        await response(scope, receive, send)

    # Wrap with 50ms timeout
    middleware = RequestTimeoutMiddleware(slow_app, timeout_seconds=0.05)

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/slow",
        "headers": [],
    }

    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        messages.append(message)

    await middleware(scope, receive, send)

    # First message should be http.response.start with status 504
    start_msg = next((m for m in messages if m["type"] == "http.response.start"), None)
    assert start_msg is not None
    assert start_msg["status"] == 504
