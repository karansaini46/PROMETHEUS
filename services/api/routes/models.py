"""Model Configurations API Routes."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db import get_db_session
from services.api.models import AuditEvent, ModelConfiguration
from services.api.schemas import (
    ModelConfigurationCreateRequest,
    ModelConfigurationResponse,
)
from services.api.security import AuthenticatedClient, verify_api_key

router = APIRouter(prefix="/models", tags=["Models"])


@router.get("", response_model=list[ModelConfigurationResponse])
async def list_model_configurations(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
    provider: str | None = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> list[ModelConfigurationResponse]:
    """List registered LLM model configurations and operational parameters."""
    query = select(ModelConfiguration)
    if provider:
        query = query.where(ModelConfiguration.provider == provider)
    if is_active is not None:
        query = query.where(ModelConfiguration.is_active == is_active)

    query = query.order_by(ModelConfiguration.created_at.desc())
    result = await db.execute(query)
    configs = result.scalars().all()

    return [ModelConfigurationResponse.model_validate(c) for c in configs]


@router.post("", response_model=ModelConfigurationResponse, status_code=status.HTTP_201_CREATED)
async def create_model_configuration(
    payload: ModelConfigurationCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> ModelConfigurationResponse:
    """Register a new LLM provider model configuration."""
    existing_stmt = select(ModelConfiguration).where(ModelConfiguration.name == payload.name)
    existing_res = await db.execute(existing_stmt)
    if existing_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Model configuration with name '{payload.name}' already exists.",
        )

    config = ModelConfiguration(
        id=str(uuid4()),
        name=payload.name,
        provider=payload.provider,
        model_name=payload.model_name,
        api_base_url=payload.api_base_url,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        context_window=payload.context_window,
        cost_per_million_input_tokens=payload.cost_per_million_input_tokens,
        cost_per_million_output_tokens=payload.cost_per_million_output_tokens,
        is_active=payload.is_active,
        settings=payload.settings,
    )
    db.add(config)

    audit = AuditEvent(
        id=str(uuid4()),
        action="MODEL_CONFIGURATION_REGISTERED",
        actor=client.client_id,
        resource_type="ModelConfiguration",
        resource_id=config.id,
        details={"name": config.name, "provider": config.provider},
    )
    db.add(audit)

    await db.commit()
    await db.refresh(config)

    return ModelConfigurationResponse.model_validate(config)


@router.get("/{model_id}", response_model=ModelConfigurationResponse)
async def get_model_configuration(
    model_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> ModelConfigurationResponse:
    """Retrieve details for a specific model configuration."""
    stmt = select(ModelConfiguration).where(
        (ModelConfiguration.id == model_id) | (ModelConfiguration.name == model_id)
    )
    res = await db.execute(stmt)
    config = res.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model configuration '{model_id}' not found.",
        )

    return ModelConfigurationResponse.model_validate(config)
