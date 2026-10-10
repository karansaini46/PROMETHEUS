"""PROMETHEUS Authoritative Database Models (SQLAlchemy 2.0).

Normalized, appropriately indexed relational models for autonomous
software engineering, execution runs, code intelligence, evaluations,
experiments, memory, and audit logging.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


# Use JSON type that falls back cleanly
JSONType = JSON().with_variant(JSONB, "postgresql")


# ==============================================================================
# Enums
# ==============================================================================


class RunStatusEnum(StrEnum):
    """Execution status for debugging and agent runs."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskStatusEnum(StrEnum):
    """Lifecycle status for software engineering tasks."""

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TaskTypeEnum(StrEnum):
    """Category of engineering task."""

    BUG_FIX = "BUG_FIX"
    FEATURE = "FEATURE"
    REFACTOR = "REFACTOR"
    BENCHMARK_EVAL = "BENCHMARK_EVAL"


class TaskPriorityEnum(StrEnum):
    """Priority level for tasks."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ToolStatusEnum(StrEnum):
    """Status of tool invocation."""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class ArtifactTypeEnum(StrEnum):
    """Types of persisted artifacts."""

    DIFF = "DIFF"
    LOG = "LOG"
    REPRODUCTION_SCRIPT = "REPRODUCTION_SCRIPT"
    TEST_REPORT = "TEST_REPORT"
    EVAL_OUTPUT = "EVAL_OUTPUT"
    OTHER = "OTHER"


# ==============================================================================
# 1. Projects
# ==============================================================================


class Project(Base):
    """Top-level organizational project or repository workspace."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    repository_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    repositories: Mapped[list["RepositoryRegistration"]] = relationship(
        "RepositoryRegistration", back_populates="project", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(
        "Task", back_populates="project", cascade="all, delete-orphan"
    )
    memory_records: Mapped[list["MemoryRecord"]] = relationship(
        "MemoryRecord", back_populates="project", cascade="all, delete-orphan"
    )


# ==============================================================================
# 2. Repository Registrations
# ==============================================================================


class RepositoryRegistration(Base):
    """Registered Git repository configuration."""

    __tablename__ = "repository_registrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    auth_type: Mapped[str] = mapped_column(String(50), default="NONE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="repositories")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="repository")


# ==============================================================================
# 3. Tasks
# ==============================================================================


class Task(Base):
    """Software engineering task or bug report."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    repository_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("repository_registrations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), default=TaskTypeEnum.BUG_FIX, index=True)
    status: Mapped[str] = mapped_column(String(50), default=TaskStatusEnum.OPEN, index=True)
    priority: Mapped[str] = mapped_column(String(50), default=TaskPriorityEnum.MEDIUM, index=True)
    base_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reproduce_command: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="tasks")
    repository: Mapped["RepositoryRegistration | None"] = relationship(
        "RepositoryRegistration", back_populates="tasks"
    )
    execution_runs: Mapped[list["ExecutionRun"]] = relationship(
        "ExecutionRun",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


# Alias for backwards compatibility
Issue = Task


# ==============================================================================
# 4. Model Configurations
# ==============================================================================


class ModelConfiguration(Base):
    """Registered LLM provider parameters, pricing, and context limits."""

    __tablename__ = "model_configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_base_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, default=0.0)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    context_window: Mapped[int] = mapped_column(Integer, default=128000)
    cost_per_million_input_tokens: Mapped[float] = mapped_column(Float, default=3.0)
    cost_per_million_output_tokens: Mapped[float] = mapped_column(Float, default=15.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    runs: Mapped[list["ExecutionRun"]] = relationship(
        "ExecutionRun", back_populates="model_configuration"
    )


# ==============================================================================
# 5. Execution Runs
# ==============================================================================


class ExecutionRun(Base):
    """Autonomous agent debugging or code execution run with stable identifier."""

    __tablename__ = "execution_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_configuration_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("model_configurations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), default=RunStatusEnum.PENDING, index=True, nullable=False
    )
    model_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    iteration_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, default=0.0)
    patch_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="execution_runs")
    model_configuration: Mapped["ModelConfiguration | None"] = relationship(
        "ModelConfiguration", back_populates="runs"
    )
    steps: Mapped[list["AgentStep"]] = relationship(
        "AgentStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentStep.step_number",
    )
    tool_invocations: Mapped[list["ToolInvocation"]] = relationship(
        "ToolInvocation",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ToolInvocation.created_at",
    )
    usage_records: Mapped[list["ModelUsageRecord"]] = relationship(
        "ModelUsageRecord", back_populates="run", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact", back_populates="run", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent", back_populates="run", cascade="all, delete-orphan"
    )


# Alias for backwards compatibility
Run = ExecutionRun


# ==============================================================================
# 6. Agent Steps
# ==============================================================================


class AgentStep(Base):
    """Discrete reasoning step in an agent execution loop."""

    __tablename__ = "agent_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("execution_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING")
    thought: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    run: Mapped["ExecutionRun"] = relationship("ExecutionRun", back_populates="steps")
    tool_invocations: Mapped[list["ToolInvocation"]] = relationship(
        "ToolInvocation", back_populates="step"
    )


# ==============================================================================
# 7. Tool Invocations
# ==============================================================================


class ToolInvocation(Base):
    """Detailed record of a tool call (grep, AST query, sandbox test, patch)."""

    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("execution_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    step_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_steps.id", ondelete="SET NULL"), index=True, nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(50), default=ToolStatusEnum.SUCCESS)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    run: Mapped["ExecutionRun"] = relationship("ExecutionRun", back_populates="tool_invocations")
    step: Mapped["AgentStep | None"] = relationship("AgentStep", back_populates="tool_invocations")


# ==============================================================================
# 8. Model Usage Records
# ==============================================================================


class ModelUsageRecord(Base):
    """Per-call token tally and cost accounting."""

    __tablename__ = "model_usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("execution_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_configuration_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("model_configurations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    step_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_steps.id", ondelete="SET NULL"), index=True, nullable=True
    )
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    run: Mapped["ExecutionRun"] = relationship("ExecutionRun", back_populates="usage_records")


# ==============================================================================
# 9. Artifacts
# ==============================================================================


class Artifact(Base):
    """Persisted output file, patch, log, or reproduction script."""

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("execution_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(100), default="text/plain")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    run: Mapped["ExecutionRun"] = relationship("ExecutionRun", back_populates="artifacts")


# ==============================================================================
# 10. Evaluation Datasets
# ==============================================================================


class EvaluationDataset(Base):
    """Benchmark dataset definition (e.g. SWE-bench Lite, HumanEval)."""

    __tablename__ = "evaluation_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    cases: Mapped[list["EvaluationCase"]] = relationship(
        "EvaluationCase", back_populates="dataset", cascade="all, delete-orphan"
    )
    runs: Mapped[list["EvaluationRun"]] = relationship(
        "EvaluationRun", back_populates="dataset", cascade="all, delete-orphan"
    )


# ==============================================================================
# 11. Evaluation Cases
# ==============================================================================


class EvaluationCase(Base):
    """Specific benchmark problem instance with validation oracle."""

    __tablename__ = "evaluation_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    instance_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    test_patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    hints_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("dataset_id", "instance_id", name="uq_eval_case_instance"),)

    # Relationships
    dataset: Mapped["EvaluationDataset"] = relationship("EvaluationDataset", back_populates="cases")


# ==============================================================================
# 12. Evaluation Runs
# ==============================================================================


class EvaluationRun(Base):
    """Execution of a benchmark suite across multiple instances."""

    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    model_configuration_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("model_configurations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    summary_metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    dataset: Mapped["EvaluationDataset"] = relationship("EvaluationDataset", back_populates="runs")
    results: Mapped[list["ExperimentResult"]] = relationship(
        "ExperimentResult", back_populates="evaluation_run"
    )


# ==============================================================================
# 13. Experiment Definitions
# ==============================================================================


class ExperimentDefinition(Base):
    """Specification of a comparative evaluation or agent configuration test."""

    __tablename__ = "experiment_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_configuration_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("model_configurations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    results: Mapped[list["ExperimentResult"]] = relationship(
        "ExperimentResult", back_populates="experiment", cascade="all, delete-orphan"
    )


# ==============================================================================
# 14. Experiment Results
# ==============================================================================


class ExperimentResult(Base):
    """Measured metric or outcome from an experiment trial."""

    __tablename__ = "experiment_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    experiment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("experiment_definitions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    evaluation_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("evaluation_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("execution_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    experiment: Mapped["ExperimentDefinition"] = relationship(
        "ExperimentDefinition", back_populates="results"
    )
    evaluation_run: Mapped["EvaluationRun | None"] = relationship(
        "EvaluationRun", back_populates="results"
    )


# ==============================================================================
# 15. Memory Records
# ==============================================================================


class MemoryRecord(Base):
    """Long-term memory, code intelligence snippets, or lessons learned."""

    __tablename__ = "memory_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("execution_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    project: Mapped["Project | None"] = relationship("Project", back_populates="memory_records")


# ==============================================================================
# 16. Audit Events
# ==============================================================================


class AuditEvent(Base):
    """Immutable audit log for security, configuration, and execution tracking."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("execution_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), default="system")
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    run: Mapped["ExecutionRun | None"] = relationship("ExecutionRun", back_populates="audit_events")


# Alias for backwards compatibility
AuditLog = AuditEvent
