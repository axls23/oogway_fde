"""Postgres access for ingest: idempotent episode/chunk upsert and
ingest_runs bookkeeping. Governed by ../contracts/schema.sql alone.
"""

from __future__ import annotations

import datetime as dt
import logging

import asyncpg

from chunker import Chunk
from transcript import Frontmatter

logger = logging.getLogger("ingest.db")


def normalize_dsn(url: str) -> str:
    """asyncpg doesn't understand the SQLAlchemy-style `postgresql+asyncpg://`
    scheme used in .env.example / docker-compose.yml for the api service --
    strip the driver suffix so the same DATABASE_URL value works for both."""
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://") :]
    return url


async def connect(dsn: str) -> asyncpg.Connection:
    conn = await asyncpg.connect(normalize_dsn(dsn))
    await _register_vector_codec(conn)
    return conn


async def _register_vector_codec(conn: asyncpg.Connection) -> None:
    """pgvector's `vector` column type has no built-in asyncpg codec; teach
    asyncpg to encode a Python list[float] as pgvector's text I/O format
    ("[0.1,0.2,...]") and decode the same way."""

    def _encode(value: list[float]) -> str:
        return "[" + ",".join(repr(float(x)) for x in value) + "]"

    def _decode(raw: str) -> list[float]:
        raw = raw.strip()
        if raw in ("", "[]"):
            return []
        return [float(x) for x in raw.strip("[]").split(",")]

    await conn.set_type_codec(
        "vector",
        encoder=_encode,
        decoder=_decode,
        schema="public",
        format="text",
    )


async def get_existing_hash(conn: asyncpg.Connection, source_path: str) -> str | None:
    row = await conn.fetchrow("SELECT content_hash FROM episodes WHERE source_path = $1", source_path)
    return row["content_hash"] if row else None


async def upsert_episode(
    conn: asyncpg.Connection,
    fm: Frontmatter,
    source_path: str,
    content_hash: str,
) -> int:
    """Insert or update the episodes row, keyed on the unique `source_path`.
    Returns the episode id."""
    publish_date: dt.date | None = None
    if fm.publish_date:
        try:
            publish_date = dt.date.fromisoformat(fm.publish_date)
        except ValueError:
            logger.warning("unparseable publish_date %r for %s, storing NULL", fm.publish_date, source_path)

    row = await conn.fetchrow(
        """
        INSERT INTO episodes (guest, title, youtube_url, video_id, publish_date,
                               duration_seconds, source_path, content_hash)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (source_path) DO UPDATE SET
            guest = EXCLUDED.guest,
            title = EXCLUDED.title,
            youtube_url = EXCLUDED.youtube_url,
            video_id = EXCLUDED.video_id,
            publish_date = EXCLUDED.publish_date,
            duration_seconds = EXCLUDED.duration_seconds,
            content_hash = EXCLUDED.content_hash
        RETURNING id
        """,
        fm.guest,
        fm.title,
        fm.youtube_url,
        fm.video_id,
        publish_date,
        fm.duration_seconds,
        source_path,
        content_hash,
    )
    return row["id"]


async def replace_chunks(
    conn: asyncpg.Connection,
    episode_id: int,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> None:
    """Delete all existing chunks for this episode (cascades from episodes
    via ON DELETE CASCADE only on episode delete -- here we delete chunks
    directly, which is the "changed episode -> replace its chunks" case)
    and insert the freshly chunked+embedded set, in one transaction."""
    assert len(chunks) == len(embeddings)
    async with conn.transaction():
        await conn.execute("DELETE FROM chunks WHERE episode_id = $1", episode_id)
        if not chunks:
            return
        await conn.executemany(
            """
            INSERT INTO chunks (episode_id, ordinal, text, token_count, start_seconds, embedding)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [
                (episode_id, c.ordinal, c.text, c.token_count, c.start_seconds, emb)
                for c, emb in zip(chunks, embeddings)
            ],
        )


async def start_ingest_run(conn: asyncpg.Connection, embed_model: str) -> int:
    row = await conn.fetchrow(
        "INSERT INTO ingest_runs (embed_model, status) VALUES ($1, 'running') RETURNING id",
        embed_model,
    )
    return row["id"]


async def finish_ingest_run(
    conn: asyncpg.Connection,
    run_id: int,
    episode_count: int,
    chunk_count: int,
    status: str,
) -> None:
    await conn.execute(
        """
        UPDATE ingest_runs
        SET finished_at = now(), episode_count = $2, chunk_count = $3, status = $4
        WHERE id = $1
        """,
        run_id,
        episode_count,
        chunk_count,
        status,
    )
