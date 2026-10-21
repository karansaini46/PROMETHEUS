"""Memory subsystem management API routes."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from prometheus_ai.memory.manager import MemoryManager
from prometheus_ai.memory.schema import (
    MemoryRecordCreate,
    MemoryType,
    VerificationStatus,
)
from services.api.db import get_db_session
from services.api.schemas import (
    MemoryCreateRequest,
    MemoryRecordResponse,
    MemoryVerifyRequest,
)
from services.api.security import (
    AuthenticatedClient,
    verify_action_approval,
    verify_admin_access,
    verify_api_key,
)

router = APIRouter(prefix="/memory", tags=["Memory Subsystem"])


def get_memory_manager(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MemoryManager:
    """Dependency provider injecting MemoryManager bounded to current request session."""

    async def session_factory() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return MemoryManager(session_factory=session_factory)


@router.post(
    "",
    response_model=MemoryRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a new memory",
)
async def create_memory(
    request: MemoryCreateRequest,
    manager: Annotated[MemoryManager, Depends(get_memory_manager)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> MemoryRecordResponse:
    """Create and persist a new episodic, semantic, procedural, or operational memory."""
    try:
        mem_type = MemoryType(request.memory_type)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid memory_type: '{request.memory_type}'. Must be one of {[t.value for t in MemoryType]}",
        ) from err

    try:
        ver_status = VerificationStatus(request.verification_status)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid verification_status: '{request.verification_status}'. Must be one of {[s.value for s in VerificationStatus]}",
        ) from err

    try:
        record = await manager.store(
            MemoryRecordCreate(
                memory_type=mem_type,
                key=request.key,
                content=request.content,
                project_id=request.project_id,
                task_id=request.task_id,
                run_id=request.run_id,
                repo_path=request.repo_path,
                revision=request.revision,
                evidence=request.evidence,
                confidence=request.confidence,
                verification_status=ver_status,
                is_hypothesis=request.is_hypothesis,
                expires_at=request.expires_at,
                invalidation_rules=request.invalidation_rules,
            )
        )
        return MemoryRecordResponse(**record.model_dump())
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get(
    "",
    response_model=list[MemoryRecordResponse],
    summary="Retrieve and search memories",
)
async def list_memories(
    manager: Annotated[MemoryManager, Depends(get_memory_manager)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
    query: str | None = Query(default=None, description="Lexical and semantic search query"),
    project_id: str | None = Query(default=None, description="Scope query to specific project"),
    memory_type: str | None = Query(default=None, description="Filter by memory type"),
    current_revision: str | None = Query(
        default=None, description="Version check for invalidation"
    ),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    exclude_unverified: bool = Query(default=False),
    include_cross_project: bool = Query(default=False),
    cross_project_reason: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[MemoryRecordResponse]:
    """Retrieve memories with hybrid semantic search, project boundaries, and version check."""
    try:
        mem_type_enum = MemoryType(memory_type) if memory_type else None
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid memory_type: '{memory_type}'",
        ) from err

    try:
        results = await manager.retrieve(
            query=query,
            project_id=project_id,
            memory_type=mem_type_enum,
            current_revision=current_revision,
            min_confidence=min_confidence,
            exclude_unverified=exclude_unverified,
            include_cross_project=include_cross_project,
            cross_project_reason=cross_project_reason,
            limit=limit,
        )
        return [MemoryRecordResponse(**m.model_dump()) for m in results]
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get(
    "/{memory_id}",
    response_model=MemoryRecordResponse,
    summary="Inspect a memory record by ID",
)
async def get_memory(
    memory_id: str,
    manager: Annotated[MemoryManager, Depends(get_memory_manager)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> MemoryRecordResponse:
    """Inspect memory provenance, confidence, and verification rules."""
    record = await manager.inspect(memory_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record '{memory_id}' not found.",
        )
    return MemoryRecordResponse(**record.model_dump())


@router.post(
    "/{memory_id}/verify",
    response_model=MemoryRecordResponse,
    summary="Promote memory to verified",
)
async def verify_memory(
    memory_id: str,
    request: MemoryVerifyRequest,
    manager: Annotated[MemoryManager, Depends(get_memory_manager)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> MemoryRecordResponse:
    """Promote an unverified memory to verified status backed by empirical evidence."""
    try:
        updated = await manager.promote_to_verified(
            memory_id=memory_id,
            evidence=request.evidence,
            verified_by_run_id=request.verified_by_run_id,
        )
        return MemoryRecordResponse(**updated.model_dump())
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record '{memory_id}' not found.",
        ) from err
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a memory record (Admin Only)",
)
async def delete_memory(
    memory_id: str,
    manager: Annotated[MemoryManager, Depends(get_memory_manager)],
    client: Annotated[AuthenticatedClient, Depends(verify_admin_access)],
    approval: Annotated[bool, Depends(verify_action_approval)],
) -> None:
    """Administrative deletion of a memory record with explicit approval check."""
    deleted = await manager.delete(memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record '{memory_id}' not found.",
        )


@router.post(
    "/projects/{project_id}/invalidate",
    summary="Invalidate project memories by revision (Admin Only)",
)
async def invalidate_by_revision(
    project_id: str,
    revision: Annotated[str, Query(description="New repository commit SHA")],
    manager: Annotated[MemoryManager, Depends(get_memory_manager)],
    client: Annotated[AuthenticatedClient, Depends(verify_admin_access)],
    approval: Annotated[bool, Depends(verify_action_approval)],
) -> dict[str, int]:
    """Administrative invalidation of memories with explicit approval check."""
    count = await manager.invalidate_by_revision(project_id=project_id, new_revision=revision)
    return {"invalidated_count": count}
