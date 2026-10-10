"""Experiments and Evaluation Results API Routes."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db import get_db_session
from services.api.models import (
    AuditEvent,
    EvaluationRun,
    ExperimentDefinition,
    ExperimentResult,
)
from services.api.schemas import (
    EvaluationRunResponse,
    ExperimentCreateRequest,
    ExperimentResponse,
    ExperimentResultResponse,
)
from services.api.security import AuthenticatedClient, verify_api_key

router = APIRouter(tags=["Experiments & Evaluations"])


# ==============================================================================
# Experiments
# ==============================================================================


@router.get("/experiments", response_model=list[ExperimentResponse])
async def list_experiments(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
    is_active: Annotated[bool | None, Query()] = None,
) -> list[ExperimentResponse]:
    """List experiment definitions and agent configuration hypotheses."""
    query = select(ExperimentDefinition)
    if is_active is not None:
        query = query.where(ExperimentDefinition.is_active == is_active)

    query = query.order_by(ExperimentDefinition.created_at.desc())
    result = await db.execute(query)
    experiments = result.scalars().all()

    return [ExperimentResponse.model_validate(e) for e in experiments]


@router.post(
    "/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_experiment(
    payload: ExperimentCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> ExperimentResponse:
    """Create a new experiment definition."""
    existing_stmt = select(ExperimentDefinition).where(ExperimentDefinition.name == payload.name)
    existing_res = await db.execute(existing_stmt)
    if existing_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Experiment with name '{payload.name}' already exists.",
        )

    experiment = ExperimentDefinition(
        id=str(uuid4()),
        name=payload.name,
        description=payload.description,
        hypothesis=payload.hypothesis,
        model_configuration_id=payload.model_configuration_id,
        parameters=payload.parameters,
        is_active=payload.is_active,
    )
    db.add(experiment)

    audit = AuditEvent(
        id=str(uuid4()),
        action="EXPERIMENT_CREATED",
        actor=client.client_id,
        resource_type="ExperimentDefinition",
        resource_id=experiment.id,
        details={"name": experiment.name},
    )
    db.add(audit)

    await db.commit()
    await db.refresh(experiment)

    return ExperimentResponse.model_validate(experiment)


@router.get(
    "/experiments/{experiment_id}/results",
    response_model=list[ExperimentResultResponse],
)
async def list_experiment_results(
    experiment_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> list[ExperimentResultResponse]:
    """List all results and recorded metrics for an experiment."""
    stmt = (
        select(ExperimentResult)
        .where(ExperimentResult.experiment_id == experiment_id)
        .order_by(ExperimentResult.created_at.desc())
    )
    result = await db.execute(stmt)
    results = result.scalars().all()

    return [ExperimentResultResponse.model_validate(r) for r in results]


# ==============================================================================
# Evaluations
# ==============================================================================


@router.get("/evaluations/results", response_model=list[ExperimentResultResponse])
async def list_all_evaluation_results(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
    metric_name: str | None = None,
) -> list[ExperimentResultResponse]:
    """Retrieve all benchmark and evaluation experiment results across runs."""
    query = select(ExperimentResult)
    if metric_name:
        query = query.where(ExperimentResult.metric_name == metric_name)

    query = query.order_by(ExperimentResult.created_at.desc())
    result = await db.execute(query)
    results = result.scalars().all()

    return [ExperimentResultResponse.model_validate(r) for r in results]


@router.get("/evaluations/runs", response_model=list[EvaluationRunResponse])
async def list_evaluation_runs(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
    dataset_id: str | None = None,
) -> list[EvaluationRunResponse]:
    """List SWE-bench and synthetic evaluation harness runs."""
    query = select(EvaluationRun)
    if dataset_id:
        query = query.where(EvaluationRun.dataset_id == dataset_id)

    query = query.order_by(EvaluationRun.created_at.desc())
    result = await db.execute(query)
    runs = result.scalars().all()

    return [EvaluationRunResponse.model_validate(r) for r in runs]
