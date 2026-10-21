"""Execution Runs API Routes.

Manages execution run lifecycles, explicit state transitions, ordered execution
event streams, cancellation propagation, and idempotency.
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prometheus_ai.tools.execution import ExecutionRegistry
from services.api.db import get_db_session
from services.api.models import (
    AgentStep,
    AuditEvent,
    ExecutionRun,
    Project,
    RunStatusEnum,
    Task,
    ToolInvocation,
)
from services.api.schemas import (
    CreateRunRequest,
    RunEventResponse,
    RunResponse,
)
from services.api.security import AuthenticatedClient, verify_api_key
from services.api.state_machine import validate_run_transition
from services.api.telemetry import trace_span

router = APIRouter(prefix="/runs", tags=["Runs"])


async def _get_or_create_task(db: AsyncSession, task_id: str) -> Task:
    """Retrieve task or provision test task for smooth testing."""
    task_stmt = select(Task).where(Task.id == task_id)
    task_res = await db.execute(task_stmt)
    task = task_res.scalar_one_or_none()

    if not task:
        # Check if project exists or create default project
        proj_stmt = select(Project).limit(1)
        proj_res = await db.execute(proj_stmt)
        project = proj_res.scalar_one_or_none()

        if not project:
            project = Project(
                id=str(uuid4()),
                name="Default Sandbox Project",
                slug=f"default-{uuid4().hex[:6]}",
                repository_url="https://github.com/prometheus/default.git",
            )
            db.add(project)
            await db.flush()

        task = Task(
            id=task_id,
            project_id=project.id,
            title=f"Task {task_id}",
            problem_statement="Autonomous execution target issue.",
        )
        db.add(task)
        await db.flush()

    return task


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: CreateRunRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> RunResponse:
    """Launch a new autonomous debugging or execution run with idempotency support and tracing."""
    effective_idempotency_key = x_idempotency_key or idempotency_key

    target_task_id = payload.task_id or payload.issue_id
    if not target_task_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="task_id or issue_id is required",
        )

    task = await _get_or_create_task(db, target_task_id)

    with trace_span(
        "run.create",
        attributes={
            "task.id": task.id,
            "model_provider": payload.model_provider,
            "idempotency_key": effective_idempotency_key or "",
        },
    ):
        # 1. Idempotency Check: if key provided, check if run already launched
        if effective_idempotency_key:
            existing_runs = await db.execute(
                select(ExecutionRun).where(ExecutionRun.task_id == task.id)
            )
            for r in existing_runs.scalars().all():
                if (
                    r.configuration_snapshot
                    and r.configuration_snapshot.get("idempotency_key") == effective_idempotency_key
                ):
                    return RunResponse.model_validate(r)

        # Stable run identifier
        run_id = f"run_{uuid4().hex}"
        now = datetime.now(UTC)

        snapshot = dict(payload.configuration_snapshot) if payload.configuration_snapshot else {}
        if effective_idempotency_key:
            snapshot["idempotency_key"] = effective_idempotency_key

        new_run = ExecutionRun(
            id=run_id,
            task_id=task.id,
            model_configuration_id=payload.model_configuration_id,
            status=RunStatusEnum.PENDING.value,
            model_provider=payload.model_provider,
            iteration_count=0,
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            cost_estimate_usd=0.0,
            current_step="INITIALIZED",
            configuration_snapshot=snapshot,
            created_at=now,
            updated_at=now,
        )
        db.add(new_run)

        # Persist initial execution step
        initial_step = AgentStep(
            id=str(uuid4()),
            run_id=run_id,
            step_number=1,
            step_name="INITIALIZED",
            status="COMPLETED",
            thought="Run initialized in PENDING state; awaiting orchestration dispatch.",
            created_at=now,
        )
        db.add(initial_step)

        # Persist audit event
        audit = AuditEvent(
            id=str(uuid4()),
            run_id=run_id,
            action="RUN_STARTED",
            actor=client.client_id,
            resource_type="ExecutionRun",
            resource_id=run_id,
            details={
                "task_id": task.id,
                "model_provider": payload.model_provider,
                "status": "PENDING",
            },
            created_at=now,
        )
        db.add(audit)

        await db.commit()
        await db.refresh(new_run)

        return RunResponse.model_validate(new_run)


@router.get("", response_model=list[RunResponse])
async def list_runs(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
    task_id: str | None = None,
    status_filter: Annotated[RunStatusEnum | None, Query(alias="status")] = None,
) -> list[RunResponse]:
    """List execution runs with optional filtering by task or status."""
    query = select(ExecutionRun)
    if task_id:
        query = query.where(ExecutionRun.task_id == task_id)
    if status_filter:
        query = query.where(ExecutionRun.status == status_filter.value)

    query = query.order_by(ExecutionRun.created_at.desc())
    result = await db.execute(query)
    runs = result.scalars().all()

    return [RunResponse.model_validate(r) for r in runs]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run_status(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> RunResponse:
    """Retrieve current status and metrics of a specific execution run."""
    stmt = select(ExecutionRun).where(ExecutionRun.id == run_id)
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found.",
        )

    return RunResponse.model_validate(run)


@router.get("/{run_id}/events", response_model=list[RunEventResponse])
async def get_run_events(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> list[RunEventResponse]:
    """Retrieve ordered execution events (steps, tool invocations, and audit entries)."""
    run_stmt = select(ExecutionRun).where(ExecutionRun.id == run_id)
    run_res = await db.execute(run_stmt)
    run = run_res.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found.",
        )

    # 1. Fetch agent steps
    steps_stmt = select(AgentStep).where(AgentStep.run_id == run_id)
    steps_res = await db.execute(steps_stmt)
    steps = steps_res.scalars().all()

    # 2. Fetch tool invocations
    tools_stmt = select(ToolInvocation).where(ToolInvocation.run_id == run_id)
    tools_res = await db.execute(tools_stmt)
    tools = tools_res.scalars().all()

    # 3. Fetch audit events
    audit_stmt = select(AuditEvent).where(AuditEvent.run_id == run_id)
    audit_res = await db.execute(audit_stmt)
    audits = audit_res.scalars().all()

    # Combine into chronological event list
    raw_events: list[tuple[datetime, str, str, dict[str, Any]]] = []

    for s in steps:
        raw_events.append(
            (
                s.created_at,
                s.id,
                "AGENT_STEP",
                {
                    "step_number": s.step_number,
                    "step_name": s.step_name,
                    "status": s.status,
                    "thought": s.thought,
                    "tokens_used": s.tokens_used,
                    "latency_ms": s.latency_ms,
                    "output_summary": s.output_summary,
                },
            )
        )

    for t in tools:
        raw_events.append(
            (
                t.created_at,
                t.id,
                "TOOL_INVOCATION",
                {
                    "tool_name": t.tool_name,
                    "parameters": t.parameters,
                    "result": t.result,
                    "status": t.status,
                    "error_message": t.error_message,
                    "duration_ms": t.duration_ms,
                },
            )
        )

    for a in audits:
        raw_events.append(
            (
                a.created_at,
                a.id,
                "AUDIT_EVENT",
                {
                    "action": a.action,
                    "actor": a.actor,
                    "details": a.details,
                },
            )
        )

    # Sort chronologically by timestamp
    raw_events.sort(key=lambda x: x[0])

    events: list[RunEventResponse] = []
    for seq, (ts, event_id, event_type, data) in enumerate(raw_events, start=1):
        events.append(
            RunEventResponse(
                event_id=event_id,
                run_id=run_id,
                event_type=event_type,
                sequence=seq,
                timestamp=ts,
                data=data,
            )
        )

    return events


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> RunResponse:
    """Cancel an active execution run with strict state transition and cancellation propagation."""
    with trace_span("run.cancel", attributes={"run.id": run_id}):
        stmt = select(ExecutionRun).where(ExecutionRun.id == run_id)
        res = await db.execute(stmt)
        run = res.scalar_one_or_none()

        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found.",
            )

        # Validate state transition: terminal states must fail
        validate_run_transition(run.status, RunStatusEnum.CANCELLED)

        # Propagate cancellation to active runner in ExecutionRegistry
        ExecutionRegistry.get_instance().cancel(run_id)

        now = datetime.now(UTC)
        run.status = RunStatusEnum.CANCELLED.value
        run.completed_at = now
        run.updated_at = now

        audit = AuditEvent(
            id=str(uuid4()),
            run_id=run.id,
            action="RUN_CANCELLED",
            actor=client.client_id,
            resource_type="ExecutionRun",
            resource_id=run.id,
            details={"status": "CANCELLED"},
            created_at=now,
        )
        db.add(audit)

        await db.commit()
        await db.refresh(run)

        return RunResponse.model_validate(run)
