"""Idempotency tests, run against a real Postgres (contracts/schema.sql
applied) rather than a mocked DB layer -- pgvector's `vector` type and the
ON CONFLICT upsert are exactly the kind of thing a mock would paper over.

Point INGEST_TEST_DATABASE_URL at a scratch database with contracts/schema.sql
already applied (see ../CLAUDE.md / the report for the podman command used
during development). Tests skip cleanly if it isn't reachable, so the suite
still runs (minus this file's coverage) in an environment without Postgres.
"""

from __future__ import annotations

import os

import asyncpg
import pytest

import db
from chunker import Chunk
from transcript import Frontmatter

TEST_DATABASE_URL = os.environ.get(
    "INGEST_TEST_DATABASE_URL",
    "postgresql://lenny:lenny@localhost:5434/lenny_growth_assistant",
)

FAKE_SOURCE_PATH = "episodes/__test_fixture_idempotency__/transcript.md"


@pytest.fixture
async def conn():
    try:
        connection = await db.connect(TEST_DATABASE_URL)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"no reachable test Postgres at {TEST_DATABASE_URL}: {exc}")
        return
    try:
        yield connection
    finally:
        await connection.execute("DELETE FROM episodes WHERE source_path = $1", FAKE_SOURCE_PATH)
        await connection.close()


def _fake_embedding() -> list[float]:
    return [0.001] * 768


def _fake_frontmatter(title: str = "Test Episode") -> Frontmatter:
    return Frontmatter(
        guest="Test Guest",
        title=title,
        youtube_url="https://example.com/watch?v=fake",
        video_id="fake",
        publish_date="2024-01-01",
        duration_seconds=100,
    )


async def test_get_existing_hash_none_when_absent(conn: asyncpg.Connection):
    result = await db.get_existing_hash(conn, FAKE_SOURCE_PATH)
    assert result is None


async def test_upsert_then_hash_matches(conn: asyncpg.Connection):
    fm = _fake_frontmatter()
    episode_id = await db.upsert_episode(conn, fm, FAKE_SOURCE_PATH, "hash-v1")
    assert episode_id is not None

    stored_hash = await db.get_existing_hash(conn, FAKE_SOURCE_PATH)
    assert stored_hash == "hash-v1"


async def test_unchanged_hash_means_no_reingest_decision(conn: asyncpg.Connection):
    """This is the idempotency contract itself: ingest.py's run() loop
    compares get_existing_hash() to the freshly computed content_hash and
    skips re-embedding when they match. We assert that contract directly at
    the DB layer here (the CLI-level behavior is exercised in
    test_ingest_cli.py, which additionally requires a reachable Ollama)."""
    fm = _fake_frontmatter()
    await db.upsert_episode(conn, fm, FAKE_SOURCE_PATH, "same-hash")

    existing = await db.get_existing_hash(conn, FAKE_SOURCE_PATH)
    freshly_computed = "same-hash"
    assert existing == freshly_computed  # -> caller would skip

    freshly_computed_after_edit = "different-hash"
    assert existing != freshly_computed_after_edit  # -> caller would re-embed


async def test_changed_hash_updates_row_and_replaces_chunks(conn: asyncpg.Connection):
    fm = _fake_frontmatter(title="Version 1")
    episode_id = await db.upsert_episode(conn, fm, FAKE_SOURCE_PATH, "hash-v1")

    chunks_v1 = [Chunk(ordinal=0, text="first version text", token_count=3, start_seconds=0)]
    await db.replace_chunks(conn, episode_id, chunks_v1, [_fake_embedding()])

    row_count = await conn.fetchval("SELECT COUNT(*) FROM chunks WHERE episode_id = $1", episode_id)
    assert row_count == 1

    # Simulate a changed transcript: same source_path, new content_hash,
    # new title, different chunk set.
    fm_v2 = _fake_frontmatter(title="Version 2")
    episode_id_v2 = await db.upsert_episode(conn, fm_v2, FAKE_SOURCE_PATH, "hash-v2")
    assert episode_id_v2 == episode_id  # same row, keyed on source_path

    chunks_v2 = [
        Chunk(ordinal=0, text="second version chunk one", token_count=4, start_seconds=0),
        Chunk(ordinal=1, text="second version chunk two", token_count=4, start_seconds=30),
    ]
    await db.replace_chunks(conn, episode_id, chunks_v2, [_fake_embedding(), _fake_embedding()])

    row_count = await conn.fetchval("SELECT COUNT(*) FROM chunks WHERE episode_id = $1", episode_id)
    assert row_count == 2  # old chunk replaced, not appended

    stored_title = await conn.fetchval("SELECT title FROM episodes WHERE id = $1", episode_id)
    assert stored_title == "Version 2"

    stored_hash = await db.get_existing_hash(conn, FAKE_SOURCE_PATH)
    assert stored_hash == "hash-v2"


async def test_ingest_runs_lifecycle(conn: asyncpg.Connection):
    run_id = await db.start_ingest_run(conn, "nomic-embed-text")
    status = await conn.fetchval("SELECT status FROM ingest_runs WHERE id = $1", run_id)
    assert status == "running"

    await db.finish_ingest_run(conn, run_id, episode_count=5, chunk_count=42, status="ok")
    row = await conn.fetchrow("SELECT status, episode_count, chunk_count, finished_at FROM ingest_runs WHERE id = $1", run_id)
    assert row["status"] == "ok"
    assert row["episode_count"] == 5
    assert row["chunk_count"] == 42
    assert row["finished_at"] is not None


def test_normalize_dsn_strips_asyncpg_driver_suffix():
    assert (
        db.normalize_dsn("postgresql+asyncpg://lenny:lenny@db:5432/lenny_growth_assistant")
        == "postgresql://lenny:lenny@db:5432/lenny_growth_assistant"
    )
    # Already-plain DSNs pass through unchanged.
    plain = "postgresql://lenny:lenny@localhost:5432/lenny_growth_assistant"
    assert db.normalize_dsn(plain) == plain
