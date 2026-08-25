"""Orchestrates one chat turn: persist user message -> condense -> retrieve
-> (abstain | call agent) -> persist assistant message + citations ->
stream SSE frames. Kept out of routers/sessions.py so the router stays a
thin HTTP/DB-session adapter (api/CLAUDE.md: one concern per file).

Ordering note on resilience (architecture.md §11, AC10): condensation and
retrieval both make a real Ollama call and both happen BEFORE the
StreamingResponse is constructed in routers/sessions.py, so "Ollama is
down" surfaces as a clean structured 503 with the ErrorEnvelope body, not a
half-open SSE stream. Once the SSE response has actually started (i.e. once
we begin talking to the agent service), a provider failure can no longer
become an HTTP 503 — headers are already committed — so it is instead
represented as an in-band `error` SSE frame with `partial: true`, which is
this module's implementation of "stream partial answer + truncation notice
on timeout rather than hanging".
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Artifact as ArtifactRow
from app.db.models import Citation as CitationRow
from app.db.models import Message as MessageRow
from app.db.models import Session as SessionRow
from app.errors import ApiError
from app.obs.logging import log_event
from app.services import sse_frames as sse
from app.services.agent_client import stream_turn
from app.services.condense import condense
from app.services.retrieval import ScoredChunk, retrieve

ABSTAIN_TEMPLATE = (
    "I don't have grounded material on that in Lenny's Podcast corpus, so I'm "
    "not going to guess. This looks outside what's been covered on the show. "
    "If you want, try rephrasing toward a product/growth angle, or ask about "
    "a related topic the corpus does cover."
)


async def _history_rows(db: AsyncSession, session_id: uuid.UUID) -> list[MessageRow]:
    stmt = select(MessageRow).where(MessageRow.session_id == session_id).order_by(
        MessageRow.created_at
    )
    return list((await db.execute(stmt)).scalars().all())


async def run_turn(
    db: AsyncSession,
    settings: Settings,
    session: SessionRow,
    raw_content: str,
    trace_id: str,
) -> AsyncIterator[str]:
    start = time.perf_counter()
    history = await _history_rows(db, session.id)

    user_row = MessageRow(
        session_id=session.id,
        role="user",
        content=raw_content,
        trace_id=trace_id,
    )
    db.add(user_row)
    await db.flush()

    # condense() and retrieve() both call Ollama and both run before any SSE
    # bytes are written — a failure here is a clean pre-stream 503.
    _, condensed = await condense(
        raw_content, history, settings, trace_id, max_history_turns=6
    )
    user_row.rewritten_query = condensed
    await db.commit()

    result = await retrieve(db, settings, condensed, session.id, trace_id)

    yield sse.stage_frame("retrieving", None)

    if result.abstained:
        async for frame in _run_abstain(db, session, trace_id, start):
            yield frame
        return

    for rank, c in enumerate(result.chunks, start=1):
        yield sse.citation_frame(c.chunk_id, c.episode_title, c.guest, rank, round(c.score, 4))

    async for frame in _run_agent(db, settings, session, condensed, result.chunks, trace_id, start):
        yield frame


async def _run_abstain(
    db: AsyncSession, session: SessionRow, trace_id: str, start: float
) -> AsyncIterator[str]:
    yield sse.token_frame(ABSTAIN_TEMPLATE)
    latency_ms = int((time.perf_counter() - start) * 1000)
    assistant_row = MessageRow(
        session_id=session.id,
        role="assistant",
        content=ABSTAIN_TEMPLATE,
        trace_id=trace_id,
        provider=None,
        model=None,
        latency_ms=latency_ms,
        abstained=True,
    )
    db.add(assistant_row)
    await db.commit()
    log_event("turn_abstained", trace_id, session_id=str(session.id), latency_ms=latency_ms)
    yield sse.done_frame(str(assistant_row.id), latency_ms, True)


async def _run_agent(
    db: AsyncSession,
    settings: Settings,
    session: SessionRow,
    condensed_query: str,
    chunks: list[ScoredChunk],
    trace_id: str,
    start: float,
) -> AsyncIterator[str]:
    history_rows = await _history_rows(db, session.id)

    # The agent's edit_artifact tool needs the artifact_id of anything it
    # created earlier in the session, but that id only ever reached the
    # browser as an `artifact` SSE frame — MessageRow.content is built from
    # streamed prose tokens only (see the token-frame branch below), so a
    # rehydrated assistant turn otherwise carries no trace of it. Fix: note
    # it directly on the copy of history sent to the agent, keyed by which
    # message the artifact is currently attached to (creation, or the most
    # recent edit — see the message_id backfill after this function's main
    # loop). This is deliberately NOT written onto history_rows/content
    # itself — MessageOut.content is that same DB column served verbatim to
    # the browser, and this note has no business appearing in the chat
    # transcript a user reads.
    assistant_message_ids = [m.id for m in history_rows if m.role == "assistant"]
    artifacts_by_message: dict[uuid.UUID, list[ArtifactRow]] = {}
    if assistant_message_ids:
        artifact_rows = (
            await db.execute(
                select(ArtifactRow).where(ArtifactRow.message_id.in_(assistant_message_ids))
            )
        ).scalars().all()
        for artifact in artifact_rows:
            assert artifact.message_id is not None  # guaranteed by the IN() filter above
            artifacts_by_message.setdefault(artifact.message_id, []).append(artifact)

    history_payload = []
    for m in history_rows:
        if m.role == "system":
            continue
        content = m.content
        for artifact in artifacts_by_message.get(m.id, []):
            title = artifact.title or "Untitled"
            content += (
                f'\n\n[Artifact created — id: {artifact.id}, kind: {artifact.kind}, '
                f'title: "{title}". Use edit_artifact with this id to revise it.]'
            )
        history_payload.append({"role": m.role, "content": content})

    text_parts: list[str] = []
    # Citations from the agent's own mid-turn search_transcripts re-query
    # (routers/internal.py's "genuinely independent re-query" case) —
    # additive to `chunks` (the primary, pre-turn retrieval below), deduped
    # by chunk_id so a re-query that resurfaces the same chunk doesn't
    # double-cite it.
    extra_citations: list[dict[str, Any]] = []
    seen_chunk_ids = {c.chunk_id for c in chunks}
    # Artifacts the agent already persisted via POST /internal/artifacts
    # (routers/internal.py) — this loop only needs to backfill message_id
    # once the assistant message exists; the row and its sanitized content
    # already landed synchronously inside that tool call.
    pending_artifact_ids: list[uuid.UUID] = []
    partial = False
    error_code: str | None = None
    error_message: str | None = None

    try:
        async for event in stream_turn(
            settings,
            trace_id,
            str(session.id),
            history_payload,
            condensed_query,
            enabled_skills=session.enabled_skills,
        ):
            if event.type == "stage":
                stage = event.raw.get("stage")
                if stage in ("thinking", "retrieving", "drafting", "outlining", "assembling"):
                    yield sse.stage_frame(stage, event.raw.get("detail"))
            elif event.type == "token":
                delta = str(event.raw.get("delta", ""))
                text_parts.append(delta)
                yield sse.token_frame(delta)
            elif event.type == "citation":
                for c in event.raw.get("chunks", []):
                    chunk_id = c.get("chunk_id")
                    if chunk_id is None or chunk_id in seen_chunk_ids:
                        continue
                    seen_chunk_ids.add(chunk_id)
                    extra_citations.append(c)
                    yield sse.citation_frame(
                        chunk_id,
                        str(c.get("episode", "")),
                        str(c.get("guest", "")),
                        int(c.get("rank", 1)),
                        float(c.get("score", 0.0)),
                    )
            elif event.type == "artifact":
                raw_kind = str(event.raw.get("kind", "markdown"))
                if raw_kind == "markdown":
                    kind: Literal["markdown", "html"] = "markdown"
                elif raw_kind == "html":
                    kind = "html"
                else:
                    log_event(
                        "artifact_event_rejected",
                        trace_id,
                        level=30,
                        reason="bad_kind",
                        kind=raw_kind,
                    )
                    continue
                raw_id = str(event.raw.get("artifact_id", ""))
                try:
                    artifact_id = uuid.UUID(raw_id)
                except ValueError:
                    log_event(
                        "artifact_event_rejected",
                        trace_id,
                        level=30,
                        reason="bad_artifact_id",
                        artifact_id=raw_id,
                    )
                    continue
                title = str(event.raw.get("title", "Untitled"))
                pending_artifact_ids.append(artifact_id)
                yield sse.artifact_frame(str(artifact_id), kind, title)
            elif event.type == "error":
                partial = True
                error_code = str(event.raw.get("code", "AGENT_ERROR"))
                error_message = str(event.raw.get("message", "agent reported an error"))
                yield sse.error_frame(
                    error_code, error_message, bool(event.raw.get("retryable", True)), partial=True
                )
    except ApiError as exc:
        partial = True
        error_code, error_message = exc.code, exc.message
        yield sse.error_frame(exc.code, exc.message, exc.retryable, partial=True)

    latency_ms = int((time.perf_counter() - start) * 1000)
    full_text = "".join(text_parts)
    if partial and error_message:
        full_text = (full_text + f"\n\n[truncated: {error_message}]").strip()

    assistant_row = MessageRow(
        session_id=session.id,
        role="assistant",
        content=full_text or "(no response — see error frame)",
        trace_id=trace_id,
        provider=settings.llm_provider,
        model=settings.llm_model,
        latency_ms=latency_ms,
        abstained=False,
    )
    db.add(assistant_row)
    await db.flush()

    for rank, c in enumerate(chunks, start=1):
        db.add(
            CitationRow(
                message_id=assistant_row.id, chunk_id=c.chunk_id, rank=rank, score=c.score
            )
        )
    for rank, c in enumerate(extra_citations, start=len(chunks) + 1):
        db.add(
            CitationRow(
                message_id=assistant_row.id,
                chunk_id=c["chunk_id"],
                rank=rank,
                score=float(c.get("score", 0.0)),
            )
        )

    if pending_artifact_ids:
        await db.execute(
            update(ArtifactRow)
            .where(ArtifactRow.id.in_(pending_artifact_ids))
            .values(message_id=assistant_row.id)
        )

    await db.commit()
    log_event(
        "turn_complete",
        trace_id,
        session_id=str(session.id),
        latency_ms=latency_ms,
        partial=partial,
        error_code=error_code,
        citation_count=len(chunks) + len(extra_citations),
        artifact_count=len(pending_artifact_ids),
    )
    yield sse.done_frame(str(assistant_row.id), latency_ms, False)
