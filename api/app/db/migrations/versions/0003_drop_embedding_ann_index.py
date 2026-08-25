"""drop chunks_embedding_idx (ivfflat), mirrors contracts/schema.sql

Revision ID: 0003_drop_embedding_ann_index
Revises: 0002_capabilities
Create Date: 2026-08-25

`chunks_embedding_idx` (ivfflat, lists=100) was sized for a corpus "in the
tens of thousands of chunks" (architecture.md §4); the actual seeded corpus
is ~8,531 chunks / 302 episodes (ingest/seed/index.sql.gz), and
`ivfflat.probes` was never set anywhere in the codebase, so every query ran
pgvector's approximate search at the default probes=1 — visiting roughly
1/100th of the index's clusters. That is a live relevance bug, not just a
latency one: a true nearest neighbor in an unprobed cluster is invisible to
`ORDER BY embedding <=> query LIMIT k`, which can both trip false
abstentions past RETRIEVAL_FLOOR (architecture.md §7, AC3) and rank a worse
chunk into the top 4 than the corpus supports.

Rather than re-tune `lists` + `probes`, this migration drops the index
outright: without an ANN index pgvector falls back to an exact sequential
scan, which is fully correct (true nearest neighbors, always) and, at this
corpus size (~8.5k rows x 768 dims), still lands in single-digit
milliseconds — the same order of magnitude ADR-003 already assumes for the
ivfflat case. Full reasoning lives in contracts/schema.sql next to where
the index used to be declared.

`chunks_episode_idx` is untouched.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_drop_embedding_ann_index"
down_revision: str | None = "0002_capabilities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_embedding_idx")


def downgrade() -> None:
    # Restores the original (oversized, untuned) index exactly as
    # 0001_initial created it, for a clean revert path.
    op.execute(
        "CREATE INDEX chunks_embedding_idx ON chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
