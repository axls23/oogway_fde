"""add sessions.enabled_skills and extension_proposals, mirrors contracts/schema.sql

Revision ID: 0002_capabilities
Revises: 0001_initial
Create Date: 2026-08-25

Adds the per-session skill allowlist and the extension-proposal review
table backing the capabilities settings page. Hand-authored to match
0001_initial's style; see contracts/schema.sql for the DDL these mirror
and root CLAUDE.md invariant #4 for why extension_proposals is a review
queue, not a deployment mechanism.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_capabilities"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("enabled_skills", postgresql.ARRAY(sa.Text())))

    op.create_table(
        "extension_proposals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tool_names", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("status IN ('pending','approved','rejected')"),
    )


def downgrade() -> None:
    op.drop_table("extension_proposals")
    op.drop_column("sessions", "enabled_skills")
