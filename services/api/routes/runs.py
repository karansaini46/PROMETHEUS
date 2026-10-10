"""Runs management API routes."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from services.api.models import RunStatusEnum

router = APIRouter(prefix="/runs", tags=["Runs"])


class CreateRunRequest(BaseModel):
    """Payload to launch a new autonomous debugging run."""

    issue_id: str = Field(description="UUID or ID of the target issue")
    model_provider: str = Field(default="anthropic/claude-3-5-sonnet-20241022")


class RunResponse(BaseModel):
    """Details of an autonomous debugging run."""

    id: str
    issue_id: str
    status: RunStatusEnum
    model_provider: str
    iteration_count: int
    total_tokens: int
    cost_estimate_usd: float
    current_step: str | None
    created_at: str
    updated_at: str


# In-memory session store fallback when running without active DB
_RUNS_STORE: dict[str, RunResponse] = {}


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(payload: CreateRunRequest) -> RunResponse:
    """Create a new debugging run. Initial status is PENDING."""
    run_id = str(uuid4())
    now = datetime.now(UTC).isoformat()

    new_run = RunResponse(
        id=run_id,
        issue_id=payload.issue_id,
        status=RunStatusEnum.PENDING,
        model_provider=payload.model_provider,
        iteration_count=0,
        total_tokens=0,
        cost_estimate_usd=0.0,
        current_step="INITIALIZED",
        created_at=now,
        updated_at=now,
    )
    _RUNS_STORE[run_id] = new_run
    return new_run


@router.get("", response_model=list[RunResponse])
async def list_runs() -> list[RunResponse]:
    """List all active and completed debugging runs."""
    return list(_RUNS_STORE.values())


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str) -> RunResponse:
    """Fetch details for a specific run."""
    run = _RUNS_STORE.get(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found.",
        )
    return run
