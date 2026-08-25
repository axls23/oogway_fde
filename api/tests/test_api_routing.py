"""Routing and read-path coverage for endpoints nothing else exercised.

Complements the existing suites rather than repeating them:
`test_sessions_persistence.py` owns the write path and the non-abstain turn,
`test_retrieval_floor.py` owns the floor as a unit, `test_internal_artifacts.py`
owns the internal artifact write path. What had no test at all before this
file:

  * `GET /chunks/{id}` — flow F2. Clicking a citation chip expands the
    verbatim snippet from ONE indexed read, with no second model call (AC5).
    Untested, despite being the single most-used element in the UI.
  * `GET /artifacts/{id}` — the artifact read path.
  * `POST /internal/retrieve` — the agent's own entry point, and the one
    endpoint whose shared-secret guard is the boundary between "agent
    service" and "anything else on the network" (ASI03).
  * The abstention path **through the HTTP layer**. The floor is unit-tested
    thoroughly, but nothing asserted that a below-floor turn actually
    reaches the browser as an abstention and never calls the agent — which
    is what AC3 promises.
  * The shared error envelope, which the frontend switches on.

Everything here runs against the real Postgres test instance. Only the
embedding call is faked, so the suite doesn't need a live Ollama.
"""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artifact, Chunk, Episode
from app.db.models import Session as SessionRow
from app.services import retrieval as retrieval_module

# Unit vector on axis 0. A stored chunk with the same vector scores cosine
# 1.0 against it; the orthogonal vector below scores 0.0, which is how the
# abstention tests drive the floor without needing a real embedder.
MATCHING_EMBEDDING = [1.0] + [0.0] * 767
ORTHOGONAL_EMBEDDING = [0.0, 1.0] + [0.0] * 766


async def _seed_episode_and_chunk(
    db_session: AsyncSession, *, embedding: list[float] | None = None
) -> tuple[int, int]:
    """Returns (episode_id, chunk_id)."""
    episode = Episode(
        guest="Grace Hopper",
        title="Shipping Before You Are Ready",
        youtube_url="https://youtube.com/watch?v=xyz789",
        video_id="xyz789",
        source_path="episodes/grace-hopper/transcript.md",
        content_hash="hash-routing-test",
    )
    db_session.add(episode)
    await db_session.flush()
    chunk = Chunk(
        episode_id=episode.id,
        ordinal=3,
        text="The verbatim line a citation chip has to be able to show.",
        token_count=11,
        start_seconds=142,
        embedding=embedding if embedding is not None else MATCHING_EMBEDDING,
    )
    db_session.add(chunk)
    await db_session.commit()
    return episode.id, chunk.id


async def _new_session(app_client: AsyncClient) -> str:
    resp = await app_client.post("/sessions", json={"title": "routing test"})
    assert resp.status_code == 201
    return str(resp.json()["id"])


# ── GET /chunks/{id} — flow F2, AC5 ──────────────────────────────────────


async def test_get_chunk_returns_verbatim_text_and_episode_metadata(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The citation-expand path. The text must come back byte-identical to
    what was indexed — a paraphrase here would silently break the one
    guarantee the citation chip exists to make."""
    _, chunk_id = await _seed_episode_and_chunk(db_session)

    resp = await app_client.get(f"/chunks/{chunk_id}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["text"] == "The verbatim line a citation chip has to be able to show."
    assert body["ordinal"] == 3
    assert body["start_seconds"] == 142
    # Episode metadata travels with the chunk so the chip can render guest +
    # title and deep-link to the video without a second round trip.
    assert body["episode"]["guest"] == "Grace Hopper"
    assert body["episode"]["title"] == "Shipping Before You Are Ready"
    assert body["episode"]["youtube_url"] == "https://youtube.com/watch?v=xyz789"


async def test_get_chunk_unknown_id_is_404_with_error_envelope(
    app_client: AsyncClient,
) -> None:
    resp = await app_client.get("/chunks/999999")
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"]
    assert error["trace_id"]
    assert error["retryable"] is False


# ── GET /artifacts/{id} ──────────────────────────────────────────────────


async def test_get_artifact_round_trips_content_and_sanitized_flag(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    session_id = await _new_session(app_client)
    artifact = Artifact(
        session_id=uuid.UUID(session_id),
        kind="markdown",
        title="A one-pager",
        content="# Heading\n\nBody text.",
        sanitized=True,
    )
    db_session.add(artifact)
    await db_session.commit()

    resp = await app_client.get(f"/artifacts/{artifact.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "markdown"
    assert body["title"] == "A one-pager"
    assert body["content"] == "# Heading\n\nBody text."
    # The browser uses this flag to decide how much to trust the payload;
    # it must survive the read path rather than defaulting.
    assert body["sanitized"] is True


async def test_get_artifact_unknown_id_is_404(app_client: AsyncClient) -> None:
    resp = await app_client.get(f"/artifacts/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── POST /internal/retrieve — the agent's entry point ────────────────────


async def test_internal_retrieve_requires_the_shared_secret(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The token is what separates 'the agent service' from anything else
    that can reach the Compose network. Without this guard the corpus is
    readable by any container on the network."""
    await _seed_episode_and_chunk(db_session)
    session_id = await _new_session(app_client)

    resp = await app_client.post(
        "/internal/retrieve",
        json={"query": "shipping", "session_id": session_id, "k": 4},
    )
    assert resp.status_code == 401

    resp = await app_client.post(
        "/internal/retrieve",
        json={"query": "shipping", "session_id": session_id, "k": 4},
        headers={"X-Internal-Token": "not-the-configured-token"},
    )
    assert resp.status_code == 401


async def test_internal_retrieve_returns_ranked_chunks_with_metadata(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, chunk_id = await _seed_episode_and_chunk(db_session)
    session_id = await _new_session(app_client)

    async def _fake_embed(query: str, settings: object, trace_id: str) -> list[float]:
        return MATCHING_EMBEDDING

    monkeypatch.setattr(retrieval_module, "embed_query", _fake_embed)

    resp = await app_client.post(
        "/internal/retrieve",
        json={"query": "shipping before you are ready", "session_id": session_id, "k": 4},
        headers={"X-Internal-Token": "test-internal-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["abstained"] is False
    assert len(body["chunks"]) == 1

    chunk = body["chunks"][0]
    assert chunk["chunk_id"] == chunk_id
    assert chunk["rank"] == 1
    # Guest and episode come from the DB join, never from the model. This is
    # the field the model is structurally prevented from writing into.
    assert chunk["guest"] == "Grace Hopper"
    assert chunk["episode"] == "Shipping Before You Are Ready"
    assert chunk["text"]


async def test_internal_retrieve_below_floor_abstains_and_returns_no_chunks(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3 at the endpoint boundary: an orthogonal query vector scores 0.0,
    far under the floor, so the response must carry abstained=true AND an
    empty chunk list — not low-scoring chunks the caller might still use."""
    await _seed_episode_and_chunk(db_session, embedding=MATCHING_EMBEDDING)
    session_id = await _new_session(app_client)

    async def _fake_embed(query: str, settings: object, trace_id: str) -> list[float]:
        return ORTHOGONAL_EMBEDDING

    monkeypatch.setattr(retrieval_module, "embed_query", _fake_embed)

    resp = await app_client.post(
        "/internal/retrieve",
        json={"query": "how do I bake sourdough", "session_id": session_id, "k": 4},
        headers={"X-Internal-Token": "test-internal-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["abstained"] is True
    assert body["chunks"] == []
    assert body["floor"] > 0


# ── Abstention through the HTTP/SSE layer — AC3 end to end ───────────────


def _parse_sse(raw: str) -> list[tuple[str, dict[str, object]]]:
    """Minimal SSE reader: returns [(event_name, parsed_data), ...]."""
    frames: list[tuple[str, dict[str, object]]] = []
    for block in raw.split("\n\n"):
        event: str | None = None
        data: str | None = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        if event and data is not None:
            frames.append((event, json.loads(data)))
    return frames


async def test_below_floor_turn_abstains_without_ever_calling_the_agent(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guarantee AC3 actually makes to a user: ask something the corpus
    doesn't cover and the model is never consulted at all.

    Note there is no fake_agent fixture requested here on purpose. If the
    abstention path regressed into calling the agent, AGENT_BASE_URL would
    point at a dead port and the turn would fail loudly rather than quietly
    producing a plausible answer.
    """
    await _seed_episode_and_chunk(db_session, embedding=MATCHING_EMBEDDING)
    session_id = await _new_session(app_client)

    async def _fake_embed(query: str, settings: object, trace_id: str) -> list[float]:
        return ORTHOGONAL_EMBEDDING

    monkeypatch.setattr(retrieval_module, "embed_query", _fake_embed)

    resp = await app_client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "What is the best way to bake sourdough bread?"},
    )
    assert resp.status_code == 200
    frames = _parse_sse(resp.text)
    kinds = [name for name, _ in frames]

    # The turn completes normally — abstention is a success state, not an error.
    assert "done" in kinds
    assert "error" not in kinds
    # And it is marked as an abstention so the UI can render the calm
    # "outside the corpus" card rather than a normal answer.
    done_payload = next(payload for name, payload in frames if name == "done")
    assert done_payload["abstained"] is True
    # No citations may be emitted for a turn that retrieved nothing.
    assert "citation" not in kinds


async def test_abstained_turn_is_persisted_as_abstained(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """messages.abstained is the column the abstention-rate metric reads.
    If the turn abstains but persists abstained=false, the metric silently
    under-reports and the eval report stops matching what users saw."""
    await _seed_episode_and_chunk(db_session, embedding=MATCHING_EMBEDDING)
    session_id = await _new_session(app_client)

    async def _fake_embed(query: str, settings: object, trace_id: str) -> list[float]:
        return ORTHOGONAL_EMBEDDING

    monkeypatch.setattr(retrieval_module, "embed_query", _fake_embed)

    await app_client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "Something the corpus has never discussed."},
    )

    detail = (await app_client.get(f"/sessions/{session_id}")).json()
    assistant = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["abstained"] is True
    assert assistant[0]["citations"] == []


# ── Session routing / not-found consistency ──────────────────────────────


async def test_posting_a_message_to_an_unknown_session_is_404(
    app_client: AsyncClient,
) -> None:
    resp = await app_client.post(
        f"/sessions/{uuid.uuid4()}/messages", json={"content": "hello"}
    )
    assert resp.status_code == 404


async def test_session_scoped_reads_do_not_leak_across_sessions(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC6 from the read side: an artifact created under session A must not
    appear in session B's detail payload."""
    session_a = await _new_session(app_client)
    session_b = await _new_session(app_client)

    db_session.add(
        Artifact(
            session_id=uuid.UUID(session_a),
            kind="markdown",
            title="A's artifact",
            content="private to A",
            sanitized=True,
        )
    )
    await db_session.commit()

    detail_b = (await app_client.get(f"/sessions/{session_b}")).json()
    assert "A's artifact" not in json.dumps(detail_b)


async def test_deleting_a_session_removes_its_artifacts_too(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The UI warns that delete is unrecoverable; this is the cascade that
    makes that warning true for artifacts specifically."""
    session_id = await _new_session(app_client)
    artifact = Artifact(
        session_id=uuid.UUID(session_id),
        kind="html",
        title="doomed",
        content="<p>bye</p>",
        sanitized=True,
    )
    db_session.add(artifact)
    await db_session.commit()
    artifact_id = artifact.id

    assert (await app_client.get(f"/artifacts/{artifact_id}")).status_code == 200

    resp = await app_client.delete(f"/sessions/{session_id}")
    assert resp.status_code == 204

    db_session.expire_all()
    assert (await app_client.get(f"/artifacts/{artifact_id}")).status_code == 404
    assert (await app_client.get(f"/sessions/{session_id}")).status_code == 404


async def test_session_row_is_gone_from_the_database_after_delete(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    session_id = await _new_session(app_client)
    await app_client.delete(f"/sessions/{session_id}")
    db_session.expire_all()
    assert await db_session.get(SessionRow, uuid.UUID(session_id)) is None
