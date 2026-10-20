"""PROMETHEUS Pydantic v2 API Validation Schemas.

Enforces strict input validation, forbids unexpected extra fields to prevent
mass assignment, and produces standardized JSON outputs.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from services.api.models import (
    RunStatusEnum,
    TaskPriorityEnum,
    TaskStatusEnum,
    TaskTypeEnum,
)

# ==============================================================================
# Common & Pagination
# ==============================================================================


class PaginatedResponse[T](BaseModel):
    """Standardized paginated list wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==============================================================================
# Tasks Schemas
# ==============================================================================


class TaskCreateRequest(BaseModel):
    """Payload to register a new software engineering task."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=36, description="Project identifier")
    title: str = Field(min_length=3, max_length=255, description="Short summary of task or bug")
    problem_statement: str = Field(min_length=5, description="Full problem or bug description")
    task_type: TaskTypeEnum = Field(default=TaskTypeEnum.BUG_FIX)
    priority: TaskPriorityEnum = Field(default=TaskPriorityEnum.MEDIUM)
    repository_id: str | None = Field(default=None, max_length=36)
    base_commit: str | None = Field(default=None, max_length=40)
    reproduce_command: str | None = Field(default=None, max_length=1024)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdateRequest(BaseModel):
    """Payload to update an existing task."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=255)
    problem_statement: str | None = Field(default=None, min_length=5)
    status: TaskStatusEnum | None = Field(default=None)
    priority: TaskPriorityEnum | None = Field(default=None)
    base_commit: str | None = Field(default=None, max_length=40)
    reproduce_command: str | None = Field(default=None, max_length=1024)
    metadata: dict[str, Any] | None = Field(default=None)


class TaskResponse(BaseModel):
    """Detailed information for a software engineering task."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    repository_id: str | None
    title: str
    problem_statement: str
    task_type: str
    status: str
    priority: str
    base_commit: str | None
    reproduce_command: str | None
    metadata_json: dict[str, Any] = Field(alias="metadata", default_factory=dict)
    created_at: datetime
    updated_at: datetime
    runs_count: int = 0
    latest_run_status: str | None = None


# ==============================================================================
# Execution Runs Schemas
# ==============================================================================


class CreateRunRequest(BaseModel):
    """Payload to start a new execution run."""

    model_config = ConfigDict(extra="forbid")

    task_id: str | None = Field(default=None, description="Target task UUID")
    issue_id: str | None = Field(
        default=None, description="Alias for task_id for backwards compatibility"
    )
    model_configuration_id: str | None = Field(default=None, max_length=36)
    model_provider: str = Field(
        default="anthropic/claude-3-5-sonnet-20241022",
        min_length=2,
        max_length=100,
    )
    configuration_snapshot: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def validate_task_reference(cls, data: Any) -> Any:
        if isinstance(data, dict):
            task_id = data.get("task_id")
            issue_id = data.get("issue_id")
            if not task_id and not issue_id:
                raise ValueError("Either 'task_id' or 'issue_id' must be provided.")
            if not task_id and issue_id:
                data["task_id"] = issue_id
        return data


class RunResponse(BaseModel):
    """Details and status of an execution run."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    model_configuration_id: str | None = None
    status: RunStatusEnum
    model_provider: str
    iteration_count: int
    total_tokens: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_estimate_usd: float
    current_step: str | None = None
    patch_diff: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def issue_id(self) -> str:
        """Backwards compatibility alias for issue_id."""
        return self.task_id


class RunEventResponse(BaseModel):
    """Chronological execution event entry (step, tool, or audit event)."""

    event_id: str
    run_id: str
    event_type: str
    sequence: int
    timestamp: datetime
    data: dict[str, Any]


# ==============================================================================
# Model Configurations Schemas
# ==============================================================================


class ModelConfigurationCreateRequest(BaseModel):
    """Payload to register a new model configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100, description="Unique model handle")
    provider: str = Field(min_length=2, max_length=50, description="Provider identifier")
    model_name: str = Field(min_length=2, max_length=255, description="Upstream model name")
    api_base_url: str | None = Field(default=None, max_length=1024)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    context_window: int = Field(default=128000, ge=1)
    cost_per_million_input_tokens: float = Field(default=3.0, ge=0.0)
    cost_per_million_output_tokens: float = Field(default=15.0, ge=0.0)
    is_active: bool = Field(default=True)
    settings: dict[str, Any] = Field(default_factory=dict)


class ModelConfigurationResponse(BaseModel):
    """Registered model configuration details."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider: str
    model_name: str
    api_base_url: str | None
    temperature: float
    max_tokens: int
    context_window: int
    cost_per_million_input_tokens: float
    cost_per_million_output_tokens: float
    is_active: bool
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ==============================================================================
# Experiments & Evaluations Schemas
# ==============================================================================


class ExperimentCreateRequest(BaseModel):
    """Payload to register an experiment definition."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None)
    hypothesis: str | None = Field(default=None)
    model_configuration_id: str | None = Field(default=None, max_length=36)
    parameters: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = Field(default=True)


class ExperimentResponse(BaseModel):
    """Experiment definition details."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    hypothesis: str | None
    model_configuration_id: str | None
    parameters: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ExperimentResultResponse(BaseModel):
    """Measured metric result from an experiment."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    experiment_id: str
    evaluation_run_id: str | None
    run_id: str | None
    metric_name: str
    metric_value: float
    details: dict[str, Any]
    created_at: datetime


class EvaluationRunResponse(BaseModel):
    """Evaluation benchmark run details."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    model_configuration_id: str | None
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    total_cost_usd: float
    summary_metrics: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


# ==============================================================================
# Memory Schemas
# ==============================================================================


class MemoryCreateRequest(BaseModel):
    """Payload to record a new memory."""

    model_config = ConfigDict(extra="forbid")

    memory_type: str = Field(description="episodic, semantic, procedural, or operational")
    key: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    project_id: str | None = Field(default=None, max_length=36)
    task_id: str | None = Field(default=None, max_length=36)
    run_id: str | None = Field(default=None, max_length=36)
    repo_path: str | None = None
    revision: str | None = None
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    verification_status: str = Field(default="unverified")
    is_hypothesis: bool = False
    expires_at: datetime | None = None
    invalidation_rules: dict[str, Any] = Field(default_factory=dict)


class MemoryVerifyRequest(BaseModel):
    """Payload to verify an existing memory with evidence."""

    model_config = ConfigDict(extra="forbid")

    evidence: list[str] = Field(min_length=1, description="Empirical proof or test log references")
    verified_by_run_id: str | None = None


class MemoryRecordResponse(BaseModel):
    """Standardized memory record API response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    memory_type: str
    key: str
    content: str
    project_id: str | None
    task_id: str | None
    run_id: str | None
    repo_path: str | None
    revision: str | None
    evidence: list[str]
    confidence: float
    verification_status: str
    is_hypothesis: bool
    is_untrusted_instruction: bool
    expires_at: datetime | None
    invalidation_rules: dict[str, Any]
    created_at: datetime
    updated_at: datetime
