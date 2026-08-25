"""POST/GET /sessions, GET/DELETE /sessions/{id}, POST /sessions/{id}/messages.

The streaming handler delegates all orchestration to services/turn.py and
is a thin adapter: look up the session, hand off, wrap the async generator
in a StreamingResponse. See services/turn.py's docstring for why a
provider failure is a clean 503 before streaming starts but an in-band
`error` SSE frame once it hasn't.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Chunk, Citation, Episode
from app.db.models import Message as MessageRow
from app.db.models import Session as SessionRow
from app.db.session import get_db
from app.errors import not_found
from app.obs.tracing import new_trace_id
from app.schemas import (
    CitationOut,
    CreateSessionRequest,
    MessageOut,
    PostMessageRequest,
    SessionDetailOut,
    SessionListResponse,
    SessionOut,
    UpdateSessionCapabilitiesRequest,
)
from app.services.turn import run_turn

router = APIRouter()


def _to_session_out(row: SessionRow) -> SessionOut:
    return SessionOut(
        id=row.id,
        title=row.title,
        provider=row.provider,
        model=row.model,
        enabled_skills=row.enabled_skills,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SessionOut:
    row = SessionRow(title=body.title, provider=settings.llm_provider, model=settings.llm_model)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_session_out(row)


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)
) -> SessionListResponse:
    limit = min(limit, 200)
    total = (await db.execute(select(func.count()).select_from(SessionRow))).scalar_one()
    stmt = (
        select(SessionRow).order_by(SessionRow.created_at.desc()).limit(limit).offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return SessionListResponse(items=[_to_session_out(r) for r in rows], total=total)


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
async def get_session(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> SessionDetailOut:
    trace_id = new_trace_id()
    row = await db.get(SessionRow, session_id)
    if row is None:
        raise not_found("session", trace_id)

    messages = list(
        (
            await db.execute(
                select(MessageRow)
                .where(MessageRow.session_id == session_id)
                .order_by(MessageRow.created_at)
            )
        )
        .scalars()
        .all()
    )
    message_ids = [m.id for m in messages]

    cite_rows: Sequence[Row[Any]] = []
    if message_ids:
        cite_stmt = (
            select(
                Citation.message_id,
                Citation.chunk_id,
                Citation.rank,
                Citation.score,
                Chunk.start_seconds,
                Episode.title,
                Episode.guest,
                Episode.youtube_url,
            )
            .join(Chunk, Chunk.id == Citation.chunk_id)
            .join(Episode, Episode.id == Chunk.episode_id)
            .where(Citation.message_id.in_(message_ids))
            .order_by(Citation.message_id, Citation.rank)
        )
        cite_rows = (await db.execute(cite_stmt)).all()

    citations_by_message: dict[uuid.UUID, list[CitationOut]] = {}
    for r in cite_rows:
        citations_by_message.setdefault(r.message_id, []).append(
            CitationOut(
                chunk_id=r.chunk_id,
                episode=r.title,
                guest=r.guest,
                youtube_url=r.youtube_url,
                start_seconds=r.start_seconds,
                rank=r.rank,
                score=r.score,
            )
        )

    message_outs = [
        MessageOut(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            rewritten_query=m.rewritten_query,
            trace_id=m.trace_id,
            provider=m.provider,
            model=m.model,
            latency_ms=m.latency_ms,
            abstained=m.abstained,
            created_at=m.created_at,
            citations=citations_by_message.get(m.id, []),
        )
        for m in messages
    ]

    return SessionDetailOut(
        id=row.id,
        title=row.title,
        provider=row.provider,
        model=row.model,
        enabled_skills=row.enabled_skills,
        created_at=row.created_at,
        updated_at=row.updated_at,
        messages=message_outs,
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    trace_id = new_trace_id()
    row = await db.get(SessionRow, session_id)
    if row is None:
        raise not_found("session", trace_id)
    await db.delete(row)
    await db.commit()


@router.patch("/sessions/{session_id}/capabilities", response_model=SessionOut)
async def update_session_capabilities(
    session_id: uuid.UUID,
    body: UpdateSessionCapabilitiesRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    """Set this session's active skill allowlist. Skills carry no tools —
    see UpdateSessionCapabilitiesRequest's docstring — so this can only
    narrow what the model is told it may do, never grant new capability."""
    trace_id = new_trace_id()
    row = await db.get(SessionRow, session_id)
    if row is None:
        raise not_found("session", trace_id)
    row.enabled_skills = body.enabled_skills
    await db.commit()
    await db.refresh(row)
    return _to_session_out(row)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: uuid.UUID,
    body: PostMessageRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    trace_id = new_trace_id()
    session = await db.get(SessionRow, session_id)
    if session is None:
        raise not_found("session", trace_id)

    generator = run_turn(db, settings, session, body.content, trace_id)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"X-Trace-Id": trace_id, "Cache-Control": "no-cache"},
    )
