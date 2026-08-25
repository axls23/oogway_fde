"""services/turn.py: the agent-facing history payload must carry a note
about any artifact created earlier in the session (so edit_artifact has an
id to target), but that note must never appear in MessageRow.content —
that column is served verbatim to the browser as the chat transcript.

Uses tests/fixtures/fake_agent.py's two test-only sentinels (see its
docstring) instead of a real Pi-backed agent process, since exercising the
real create_artifact/edit_artifact tool call would require the agent
service running.
"""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Episode
from app.services import retrieval as retrieval_module
from app.services import turn as turn_module

FAKE_EMBEDDING = [1.0] + [0.0] * 767
INTERNAL_TOKEN = os.environ["AGENT_INTERNAL_TOKEN"]


async def _seed_one_chunk(db_session: AsyncSession) -> None:
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
    db_session.add(
        Chunk(
            episode_id=episode.id,
            ordinal=0,
            text="This is the verbatim transcript snippet about growth loops.",
            token_count=12,
            start_seconds=90,
            embedding=FAKE_EMBEDDING,
        )
    )
    await db_session.commit()


async def test_artifact_note_reaches_agent_but_never_the_browser(
    app_client: AsyncClient,
    db_session: AsyncSession,
    fake_agent_server: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_embed(query: str, settings: object, trace_id: str) -> list[float]:
        return FAKE_EMBEDDING

    async def _fake_condense(
        raw_message: str,
        history: list,
        settings: object,
        trace_id: str,
        max_history_turns: int = 6,
    ):
        # Turn 2 has real history, so the real condense() would make an
        # actual Ollama call — not what this test is checking. Skip it the
        # same way turn 1 already short-circuits with no history.
        return raw_message, raw_message

    monkeypatch.setattr(retrieval_module, "embed_query", _fake_embed)
    monkeypatch.setattr(turn_module, "condense", _fake_condense)
    await _seed_one_chunk(db_session)

    session_id = (await app_client.post("/sessions", json={})).json()["id"]

    # Simulate "the agent's create_artifact tool already ran and persisted
    # a row" — in production that POST happens from inside the agent
    # process mid-turn; here the test does it directly.
    created = await app_client.post(
        "/internal/artifacts",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        json={
            "session_id": session_id,
            "kind": "markdown",
            "title": "Growth Memo",
            "content": "# v1",
        },
    )
    assert created.status_code == 201
    artifact_id = created.json()["id"]
    assert created.json()["message_id"] is None  # not backfilled yet

    # Turn 1: fake_agent emits an `artifact` event for that id, as if its
    # own create_artifact tool call had just returned.
    async with app_client.stream(
        "POST",
        f"/sessions/{session_id}/messages",
        json={"content": f"__create_artifact__:{artifact_id}"},
    ) as r:
        body = b"".join([c async for c in r.aiter_bytes()]).decode()
    assert "event: artifact" in body

    backfilled = await app_client.get(f"/artifacts/{artifact_id}")
    assistant_message_id = backfilled.json()["message_id"]
    assert assistant_message_id is not None  # turn.py's message_id backfill ran

    turn1_detail = (await app_client.get(f"/sessions/{session_id}")).json()
    turn1_assistant = next(m for m in turn1_detail["messages"] if m["role"] == "assistant")
    # The note must never land in the DB column MessageOut.content serves
    # verbatim to the browser.
    assert "Artifact created" not in turn1_assistant["content"]
    assert artifact_id not in turn1_assistant["content"]

    # Turn 2: fake_agent echoes back exactly what api sent it as history.
    async with app_client.stream(
        "POST", f"/sessions/{session_id}/messages", json={"content": "__echo_history__"}
    ) as r:
        async for _ in r.aiter_bytes():
            pass

    turn2_detail = (await app_client.get(f"/sessions/{session_id}")).json()
    turn2_assistant = next(
        m
        for m in turn2_detail["messages"]
        if m["role"] == "assistant" and m["id"] != assistant_message_id
    )
    # This is the agent-facing echo, not the browser-facing column — the
    # note IS expected to show up here, carrying the real artifact_id and
    # the edit_artifact pointer, since that's the entire point of the fix.
    assert "Artifact created" in turn2_assistant["content"]
    assert artifact_id in turn2_assistant["content"]
    assert "edit_artifact" in turn2_assistant["content"]
