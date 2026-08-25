"""AC6: two concurrent sessions maintain fully independent context, and
messages persist across a backend restart (simulated here by reading rows
back through a brand-new DB connection, not the app's own session).

Also covers the full non-abstain F1 turn end-to-end against the real
Postgres test instance and the real fake_agent HTTP stub (tests/fixtures/
fake_agent.py), with only the embedding call mocked so this suite doesn't
require a live Ollama to pass `make test` in an arbitrary CI environment
(retrieval-against-real-Ollama is covered separately, clearly marked, in
tests/test_condense_integration.py).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Episode
from app.services import retrieval as retrieval_module

FAKE_EMBEDDING = [1.0] + [0.0] * 767


async def _seed_one_chunk(db_session: AsyncSession) -> int:
    episode = Episode(
        guest="Ada Lovelace",
        title="On Growth Loops",
        youtube_url="https://youtube.com/watch?v=abc123",
        video_id="abc123",
        source_path="episodes/ada-lovelace/transcript.md",
        content_hash="hash1",
    )
    db_session.add(episode)
    await db_session.flush()
    chunk = Chunk(
        episode_id=episode.id,
        ordinal=0,
        text="This is the verbatim transcript snippet about growth loops.",
        token_count=12,
        start_seconds=90,
        embedding=FAKE_EMBEDDING,
    )
    db_session.add(chunk)
    await db_session.commit()
    return chunk.id


async def test_create_list_get_session(app_client: AsyncClient) -> None:
    resp = await app_client.post("/sessions", json={"title": "My session"})
    assert resp.status_code == 201
    session = resp.json()
    assert session["provider"] == "ollama"
    assert session["title"] == "My session"

    resp = await app_client.get(f"/sessions/{session['id']}")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []

    resp = await app_client.get("/sessions")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


async def test_get_session_404_for_unknown_id(app_client: AsyncClient) -> None:
    resp = await app_client.get(f"/sessions/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_delete_session_cascades(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    resp = await app_client.post("/sessions", json={})
    session_id = resp.json()["id"]

    chunk_id = await _seed_one_chunk(db_session)
    from app.db.models import Message

    msg = Message(
        session_id=uuid.UUID(session_id),
        role="assistant",
        content="hello",
        trace_id="t1",
        abstained=False,
    )
    db_session.add(msg)
    await db_session.flush()
    from app.db.models import Citation

    db_session.add(Citation(message_id=msg.id, chunk_id=chunk_id, rank=1, score=0.9))
    await db_session.commit()

    resp = await app_client.delete(f"/sessions/{session_id}")
    assert resp.status_code == 204

    remaining_messages = (
        await db_session.execute(
            text("SELECT count(*) FROM messages WHERE session_id = :sid"),
            {"sid": session_id},
        )
    ).scalar_one()
    assert remaining_messages == 0
    remaining_citations = (
        await db_session.execute(text("SELECT count(*) FROM citations"))
    ).scalar_one()
    assert remaining_citations == 0


async def test_full_turn_persists_message_and_citations(
    app_client: AsyncClient,
    db_session: AsyncSession,
    fake_agent_server: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_embed(query: str, settings: object, trace_id: str) -> list[float]:
        return FAKE_EMBEDDING

    monkeypatch.setattr(retrieval_module, "embed_query", _fake_embed)
    await _seed_one_chunk(db_session)

    resp = await app_client.post("/sessions", json={})
    session_id = resp.json()["id"]

    async with app_client.stream(
        "POST", f"/sessions/{session_id}/messages", json={"content": "what about B2B growth?"}
    ) as stream_resp:
        assert stream_resp.status_code == 200
        body = b"".join([chunk async for chunk in stream_resp.aiter_bytes()]).decode()

    assert "event: citation" in body
    assert "event: token" in body
    assert "event: done" in body
    assert "Ada Lovelace" in body  # citation frame carries the guest name

    detail = await app_client.get(f"/sessions/{session_id}")
    messages = detail.json()["messages"]
    assert len(messages) == 2  # user + assistant
    assistant = [m for m in messages if m["role"] == "assistant"][0]
    assert assistant["abstained"] is False
    assert len(assistant["citations"]) == 1
    assert assistant["citations"][0]["guest"] == "Ada Lovelace"
    user = [m for m in messages if m["role"] == "user"][0]
    assert user["rewritten_query"] == "what about B2B growth?"  # turn 1: no history to condense


async def test_two_concurrent_sessions_independent_context(
    app_client: AsyncClient,
    db_session: AsyncSession,
    fake_agent_server: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_embed(query: str, settings: object, trace_id: str) -> list[float]:
        return FAKE_EMBEDDING

    monkeypatch.setattr(retrieval_module, "embed_query", _fake_embed)
    await _seed_one_chunk(db_session)

    session_a = (await app_client.post("/sessions", json={"title": "A"})).json()["id"]
    session_b = (await app_client.post("/sessions", json={"title": "B"})).json()["id"]

    async with app_client.stream(
        "POST", f"/sessions/{session_a}/messages", json={"content": "topic A question"}
    ) as r:
        async for _ in r.aiter_bytes():
            pass

    async with app_client.stream(
        "POST", f"/sessions/{session_b}/messages", json={"content": "topic B question"}
    ) as r:
        async for _ in r.aiter_bytes():
            pass

    detail_a = (await app_client.get(f"/sessions/{session_a}")).json()
    detail_b = (await app_client.get(f"/sessions/{session_b}")).json()

    assert len(detail_a["messages"]) == 2
    assert len(detail_b["messages"]) == 2
    contents_a = {m["content"] for m in detail_a["messages"]}
    contents_b = {m["content"] for m in detail_b["messages"]}
    assert "topic A question" in contents_a
    assert "topic A question" not in contents_b
    assert "topic B question" in contents_b
    assert "topic B question" not in contents_a


async def test_messages_persist_across_a_fresh_db_connection(
    app_client: AsyncClient,
    db_session: AsyncSession,
    fake_agent_server: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates a backend restart: read the row back through a brand-new
    engine/connection rather than the app's request-scoped session, proving
    the data actually landed in Postgres and isn't held in-process only."""
    async def _fake_embed(query: str, settings: object, trace_id: str) -> list[float]:
        return FAKE_EMBEDDING

    monkeypatch.setattr(retrieval_module, "embed_query", _fake_embed)
    await _seed_one_chunk(db_session)

    session_id = (await app_client.post("/sessions", json={})).json()["id"]
    async with app_client.stream(
        "POST", f"/sessions/{session_id}/messages", json={"content": "durability check"}
    ) as r:
        async for _ in r.aiter_bytes():
            pass

    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.conftest import TEST_DATABASE_URL

    fresh_engine = create_async_engine(TEST_DATABASE_URL)
    async with fresh_engine.connect() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM messages WHERE session_id = :sid"),
                {"sid": session_id},
            )
        ).scalar_one()
    await fresh_engine.dispose()
    assert count == 2
