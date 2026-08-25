"""Shared pytest fixtures.

Tests run against a REAL ephemeral Postgres (pgvector/pgvector:pg16) —
per the task brief, DB tests are not silently skipped or mocked away. Point
TEST_DATABASE_URL at a reachable instance; defaults to the one this task's
environment doc describes starting on localhost:5433. Migrations are run
once per test session, and each test truncates all tables in its own
transaction-scoped cleanup so tests stay independent without needing a full
migration re-run per test.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://lenny:lenny@localhost:5433/lenny_growth_assistant"
)

FAKE_AGENT_PORT = 8199

os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("AGENT_INTERNAL_TOKEN", "test-internal-token")
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
os.environ.setdefault("AGENT_BASE_URL", f"http://127.0.0.1:{FAKE_AGENT_PORT}")

TABLES = ["citations", "artifacts", "messages", "sessions", "chunks", "episodes", "ingest_runs"]


@pytest_asyncio.fixture(scope="session")
async def _migrated_db() -> AsyncIterator[None]:
    import asyncio

    from alembic import command
    from alembic.config import Config

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    await asyncio.to_thread(command.upgrade, cfg, "head")
    yield


@pytest_asyncio.fixture
async def db_session(_migrated_db: None) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        for table in TABLES:
            await session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        await session.commit()
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from app.db.session import get_db
    from app.main import app

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture(scope="session")
def fake_agent_server() -> Iterator[None]:
    """Runs tests/fixtures/fake_agent.py (the stub speaking agent_client.py's
    assumed interface) on a background thread for the whole test session,
    at the AGENT_BASE_URL set above. Real HTTP, not an in-process ASGI
    transport swap — this exercises agent_client.py's actual NDJSON parsing
    over a real socket, not just its Python-level logic."""
    import threading

    import uvicorn

    from tests.fixtures.fake_agent import app as fake_app

    config = uvicorn.Config(fake_app, host="127.0.0.1", port=FAKE_AGENT_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    import time

    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    yield
    server.should_exit = True
    thread.join(timeout=5)
