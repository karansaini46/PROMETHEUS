"""Complete PROMETHEUS backend architecture schema.

Revision ID: 002_complete_schema
Revises: 001_initial_schema
Create Date: 2026-10-10 14:30:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "002_complete_schema"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Update projects table
    op.add_column("projects", sa.Column("slug", sa.String(length=100), nullable=True))
    op.add_column("projects", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "projects",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    # Populate existing projects slug if any
    op.execute("UPDATE projects SET slug = id WHERE slug IS NULL")
    op.alter_column("projects", "slug", nullable=False)
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)

    # 2. repository_registrations table
    op.create_table(
        "repository_registrations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("repo_url", sa.String(length=1024), nullable=False),
        sa.Column("default_branch", sa.String(length=100), server_default="main"),
        sa.Column("auth_type", sa.String(length=50), server_default="NONE"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), index=True),
        sa.Column("settings", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # 3. tasks table
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "repository_id",
            sa.String(length=36),
            sa.ForeignKey("repository_registrations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False, index=True),
        sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("task_type", sa.String(length=50), server_default="BUG_FIX", index=True),
        sa.Column("status", sa.String(length=50), server_default="OPEN", index=True),
        sa.Column("priority", sa.String(length=50), server_default="MEDIUM", index=True),
        sa.Column("base_commit", sa.String(length=40), nullable=True),
        sa.Column("reproduce_command", sa.String(length=1024), nullable=True),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # 4. model_configurations table
    op.create_table(
        "model_configurations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=100), unique=True, index=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False, index=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("api_base_url", sa.String(length=1024), nullable=True),
        sa.Column("temperature", sa.Float(), server_default="0.0"),
        sa.Column("max_tokens", sa.Integer(), server_default="4096"),
        sa.Column("context_window", sa.Integer(), server_default="128000"),
        sa.Column("cost_per_million_input_tokens", sa.Float(), server_default="3.0"),
        sa.Column("cost_per_million_output_tokens", sa.Float(), server_default="15.0"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), index=True),
        sa.Column("settings", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # 5. execution_runs table
    op.create_table(
        "execution_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(length=36),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "model_configuration_id",
            sa.String(length=36),
            sa.ForeignKey("model_configurations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "status", sa.String(length=50), server_default="PENDING", index=True, nullable=False
        ),
        sa.Column("model_provider", sa.String(length=100), nullable=False),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column("iteration_count", sa.Integer(), server_default="0"),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), server_default="0"),
        sa.Column("cost_estimate_usd", sa.Float(), server_default="0.0"),
        sa.Column("patch_diff", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("configuration_snapshot", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # 6. agent_steps table
    op.create_table(
        "agent_steps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("step_number", sa.Integer(), nullable=False, index=True),
        sa.Column("step_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="RUNNING"),
        sa.Column("thought", sa.Text(), nullable=True),
        sa.Column("input_context", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), server_default="0"),
        sa.Column("latency_ms", sa.Integer(), server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
    )

    # 7. tool_invocations table
    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "step_id",
            sa.String(length=36),
            sa.ForeignKey("agent_steps.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("tool_name", sa.String(length=100), nullable=False, index=True),
        sa.Column("parameters", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("result", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(length=50), server_default="SUCCESS"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
    )

    # 8. model_usage_records table
    op.create_table(
        "model_usage_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "model_configuration_id",
            sa.String(length=36),
            sa.ForeignKey("model_configurations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "step_id",
            sa.String(length=36),
            sa.ForeignKey("agent_steps.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), server_default="0"),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("cost_usd", sa.Float(), server_default="0.0"),
        sa.Column("latency_ms", sa.Integer(), server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
    )

    # 9. artifacts table
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("artifact_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_path", sa.String(length=1024), nullable=True),
        sa.Column("size_bytes", sa.Integer(), server_default="0"),
        sa.Column("mime_type", sa.String(length=100), server_default="text/plain"),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
    )

    # 10. evaluation_datasets table
    op.create_table(
        "evaluation_datasets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), unique=True, index=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(length=50), server_default="1.0.0"),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # 11. evaluation_cases table
    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=36),
            sa.ForeignKey("evaluation_datasets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("instance_id", sa.String(length=255), nullable=False, index=True),
        sa.Column("repository_name", sa.String(length=255), nullable=False),
        sa.Column("base_commit", sa.String(length=40), nullable=False),
        sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("test_patch", sa.Text(), nullable=True),
        sa.Column("reference_patch", sa.Text(), nullable=True),
        sa.Column("hints_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("dataset_id", "instance_id", name="uq_eval_case_instance"),
    )

    # 12. evaluation_runs table
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=36),
            sa.ForeignKey("evaluation_datasets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "model_configuration_id",
            sa.String(length=36),
            sa.ForeignKey("model_configurations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("status", sa.String(length=50), server_default="PENDING", index=True),
        sa.Column("total_cases", sa.Integer(), server_default="0"),
        sa.Column("passed_cases", sa.Integer(), server_default="0"),
        sa.Column("failed_cases", sa.Integer(), server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), server_default="0.0"),
        sa.Column("summary_metrics", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
    )

    # 13. experiment_definitions table
    op.create_table(
        "experiment_definitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), unique=True, index=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column(
            "model_configuration_id",
            sa.String(length=36),
            sa.ForeignKey("model_configurations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("parameters", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # 14. experiment_results table
    op.create_table(
        "experiment_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "experiment_id",
            sa.String(length=36),
            sa.ForeignKey("experiment_definitions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "evaluation_run_id",
            sa.String(length=36),
            sa.ForeignKey("evaluation_runs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("execution_runs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("metric_name", sa.String(length=100), nullable=False, index=True),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("details", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
    )

    # 15. memory_records table
    op.create_table(
        "memory_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("execution_runs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("memory_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("key", sa.String(length=255), nullable=False, index=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # 16. audit_events table
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("execution_runs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("action", sa.String(length=100), nullable=False, index=True),
        sa.Column("actor", sa.String(length=100), server_default="system"),
        sa.Column("resource_type", sa.String(length=100), nullable=True),
        sa.Column("resource_id", sa.String(length=36), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True, index=True),
        sa.Column("details", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("memory_records")
    op.drop_table("experiment_results")
    op.drop_table("experiment_definitions")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_datasets")
    op.drop_table("artifacts")
    op.drop_table("model_usage_records")
    op.drop_table("tool_invocations")
    op.drop_table("agent_steps")
    op.drop_table("execution_runs")
    op.drop_table("model_configurations")
    op.drop_table("tasks")
    op.drop_table("repository_registrations")
    op.drop_index("ix_projects_slug", "projects")
    op.drop_column("projects", "updated_at")
    op.drop_column("projects", "description")
    op.drop_column("projects", "slug")
