"""Add vector support and embedding column to memory_records.

Revision ID: 003_add_memory_vector
Revises: 002_complete_schema
Create Date: 2026-10-13 13:45:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "003_add_memory_vector"
down_revision = "002_complete_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enable pgvector extension if available
    conn = op.get_bind()
    try:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))
    except Exception:
        # ponytail: If pgvector extension cannot be installed (e.g. non-superuser or SQLite in tests),
        # continue gracefully; the subsystem falls back to lexical / metadata search.
        pass

    # 2. Add embedding column to memory_records if not present
    try:
        from pgvector.sqlalchemy import Vector

        column_type = Vector(384)
    except ImportError:
        column_type = sa.JSON()

    # Check whether column already exists
    inspector = sa.inspect(conn)
    existing_cols = [c["name"] for c in inspector.get_columns("memory_records")]
    if "embedding" not in existing_cols:
        op.add_column("memory_records", sa.Column("embedding", column_type, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c["name"] for c in inspector.get_columns("memory_records")]
    if "embedding" in existing_cols:
        op.drop_column("memory_records", "embedding")
