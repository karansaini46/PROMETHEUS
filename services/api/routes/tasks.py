"""Software Engineering Tasks API Routes."""

import math
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db import get_db_session
from services.api.models import (
    AuditEvent,
    Project,
    Task,
    TaskPriorityEnum,
    TaskStatusEnum,
    TaskTypeEnum,
)
from services.api.schemas import (
    PaginatedResponse,
    TaskCreateRequest,
    TaskResponse,
    TaskUpdateRequest,
)
from services.api.security import AuthenticatedClient, verify_api_key
from services.api.state_machine import validate_task_transition

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> TaskResponse:
    """Register a new software engineering task or bug report."""
    # Verify project exists or auto-provision default project if it matches default/demo
    proj_stmt = select(Project).where(Project.id == payload.project_id)
    proj_res = await db.execute(proj_stmt)
    project = proj_res.scalar_one_or_none()

    if not project:
        # Check if looking for default project or create placeholder project
        proj_by_slug = await db.execute(select(Project).where(Project.slug == payload.project_id))
        project = proj_by_slug.scalar_one_or_none()

        if not project:
            # Create project automatically if ID does not exist yet to facilitate seamless bootstrap
            project = Project(
                id=payload.project_id,
                name=f"Project {payload.project_id}",
                slug=f"proj-{payload.project_id[:8]}",
                repository_url="https://github.com/prometheus/default.git",
            )
            db.add(project)
            await db.flush()

    task = Task(
        id=str(uuid4()),
        project_id=project.id,
        repository_id=payload.repository_id,
        title=payload.title,
        problem_statement=payload.problem_statement,
        task_type=payload.task_type.value,
        status=TaskStatusEnum.OPEN.value,
        priority=payload.priority.value,
        base_commit=payload.base_commit,
        reproduce_command=payload.reproduce_command,
        metadata_json=payload.metadata,
    )
    db.add(task)

    audit = AuditEvent(
        id=str(uuid4()),
        action="TASK_CREATED",
        actor=client.client_id,
        resource_type="Task",
        resource_id=task.id,
        details={"title": task.title, "task_type": task.task_type},
    )
    db.add(audit)

    await db.commit()
    await db.refresh(task)

    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        title=task.title,
        problem_statement=task.problem_statement,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        base_commit=task.base_commit,
        reproduce_command=task.reproduce_command,
        metadata=task.metadata_json or {},
        created_at=task.created_at,
        updated_at=task.updated_at,
        runs_count=0,
        latest_run_status=None,
    )


@router.get("", response_model=PaginatedResponse[TaskResponse])
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
    project_id: str | None = None,
    status_filter: Annotated[TaskStatusEnum | None, Query(alias="status")] = None,
    priority: TaskPriorityEnum | None = None,
    task_type: TaskTypeEnum | None = None,
    search: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[TaskResponse]:
    """List software engineering tasks with pagination and flexible filtering."""
    query = select(Task)

    if project_id:
        query = query.where(Task.project_id == project_id)
    if status_filter:
        query = query.where(Task.status == status_filter.value)
    if priority:
        query = query.where(Task.priority == priority.value)
    if task_type:
        query = query.where(Task.task_type == task_type.value)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Task.title.ilike(search_pattern),
                Task.problem_statement.ilike(search_pattern),
            )
        )

    # Count total matching
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Apply pagination and sorting
    offset = (page - 1) * page_size
    query = query.order_by(Task.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    tasks = result.scalars().all()

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    items = [
        TaskResponse(
            id=t.id,
            project_id=t.project_id,
            repository_id=t.repository_id,
            title=t.title,
            problem_statement=t.problem_statement,
            task_type=t.task_type,
            status=t.status,
            priority=t.priority,
            base_commit=t.base_commit,
            reproduce_command=t.reproduce_command,
            metadata=t.metadata_json or {},
            created_at=t.created_at,
            updated_at=t.updated_at,
            runs_count=len(t.execution_runs) if t.execution_runs else 0,
            latest_run_status=(t.execution_runs[-1].status if t.execution_runs else None),
        )
        for t in tasks
    ]

    return PaginatedResponse[TaskResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_details(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> TaskResponse:
    """Retrieve full details of a specific software engineering task."""
    stmt = select(Task).where(Task.id == task_id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )

    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        title=task.title,
        problem_statement=task.problem_statement,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        base_commit=task.base_commit,
        reproduce_command=task.reproduce_command,
        metadata=task.metadata_json or {},
        created_at=task.created_at,
        updated_at=task.updated_at,
        runs_count=len(task.execution_runs) if task.execution_runs else 0,
        latest_run_status=(task.execution_runs[-1].status if task.execution_runs else None),
    )


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    payload: TaskUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> TaskResponse:
    """Update task details with state transition validation."""
    stmt = select(Task).where(Task.id == task_id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )

    if payload.status is not None:
        validate_task_transition(task.status, payload.status)
        task.status = payload.status.value

    if payload.title is not None:
        task.title = payload.title
    if payload.problem_statement is not None:
        task.problem_statement = payload.problem_statement
    if payload.priority is not None:
        task.priority = payload.priority.value
    if payload.base_commit is not None:
        task.base_commit = payload.base_commit
    if payload.reproduce_command is not None:
        task.reproduce_command = payload.reproduce_command
    if payload.metadata is not None:
        task.metadata_json = payload.metadata

    audit = AuditEvent(
        id=str(uuid4()),
        action="TASK_UPDATED",
        actor=client.client_id,
        resource_type="Task",
        resource_id=task.id,
        details={"status": task.status},
    )
    db.add(audit)

    await db.commit()
    await db.refresh(task)

    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        title=task.title,
        problem_statement=task.problem_statement,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        base_commit=task.base_commit,
        reproduce_command=task.reproduce_command,
        metadata=task.metadata_json or {},
        created_at=task.created_at,
        updated_at=task.updated_at,
        runs_count=len(task.execution_runs) if task.execution_runs else 0,
        latest_run_status=(task.execution_runs[-1].status if task.execution_runs else None),
    )
