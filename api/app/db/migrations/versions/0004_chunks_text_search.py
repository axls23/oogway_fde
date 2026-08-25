"""add chunks.text_search (generated tsvector) + GIN index, mirrors contracts/schema.sql

Revision ID: 0004_chunks_text_search
Revises: 0003_drop_embedding_ann_index
Create Date: 2026-08-25

Lexical/full-text side of hybrid retrieval (api/app/services/retrieval.py
`_top_k_by_fulltext`), fused with the existing vector search via reciprocal
rank fusion. `text_search` is a `GENERATED ALWAYS AS (...) STORED` column so
Postgres keeps it in sync with `text` automatically on insert/update --
ingest never writes to it, and no backfill step is needed for existing rows
(`GENERATED ALWAYS AS ... STORED` is computed for all rows, including
pre-existing ones, at the moment the column is added).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_chunks_text_search"
down_revision: str | None = "0003_drop_embedding_ann_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chunks ADD COLUMN text_search TSVECTOR "
        "GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"
    )
    op.execute("CREATE INDEX chunks_text_search_idx ON chunks USING GIN (text_search)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_text_search_idx")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS text_search")
