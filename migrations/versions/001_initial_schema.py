"""Initial Schema: projects, issues, runs, audit_logs.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-10 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Projects table
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("repository_url", sa.String(length=1024), nullable=False),
        sa.Column("default_branch", sa.String(length=100), server_default="main"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # Issues table
    op.create_table(
        "issues",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("base_commit", sa.String(length=40), nullable=False),
        sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("reproduce_command", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # Runs table
    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("issue_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "PAUSED",
                "VERIFYING",
                "RESOLVED",
                "FAILED",
                "CANCELLED",
                name="runstatusenum",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("model_provider", sa.String(length=100), nullable=False),
        sa.Column("iteration_count", sa.Integer(), server_default="0"),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("cost_estimate_usd", sa.Float(), server_default="0.0"),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column("patch_diff", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # Audit logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("actor", sa.String(length=100), server_default="system"),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("runs")
    op.drop_table("issues")
    op.drop_table("projects")
    op.execute("DROP TYPE IF EXISTS runstatusenum")
