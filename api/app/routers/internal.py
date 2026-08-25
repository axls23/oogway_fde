"""POST /internal/retrieve, POST /internal/artifacts, PATCH
/internal/artifacts/{id} — agent-service-only, shared-secret guarded.

architecture.md §5: "Restricted to the Compose network and guarded by a
shared secret in AGENT_INTERNAL_TOKEN. It is not exposed through the
frontend proxy." This router only enforces the shared-secret check; network
restriction is a Compose/deployment concern (docker-compose.yml puts this
service on an internal network), not something Python can enforce.

No query condensation happens here — the caller (the agent's
search_transcripts tool) supplies whatever query text it has already
decided to search for. The api-side deterministic condense+retrieve for
the *primary* F1 turn happens in routers/sessions.py before the agent is
ever invoked (see services/agent_client.py's module docstring for why).
This endpoint exists so the contract in contracts/openapi.yaml is honored
and so the agent can issue a genuinely independent re-query mid-turn if its
own reasoning calls for one.

POST /internal/artifacts is a contract addition (contracts/openapi.yaml,
architecture.md §8.3): the agent's create_artifact tool has no other write
path to persist artifact content before it can emit an `artifact` SSE
frame carrying a real artifact_id. `message_id` is null at creation time
(the assistant message doesn't exist yet mid-turn) and is backfilled by
services/turn.py once that message is committed — contracts/schema.sql
already allows a null artifacts.message_id for exactly this reason.

PATCH /internal/artifacts/{id} is the same kind of contract addition, for
the agent's edit_artifact tool: revise an artifact already created earlier
in the session in place, no version history. `body.session_id` must match
the row's own session_id or the request 404s — the check exists so one
session's agent call can never rewrite another session's artifact even
though this endpoint has no per-session auth of its own beyond the shared
internal token.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Artifact as ArtifactRow
from app.db.session import get_db
from app.errors import ApiError, not_found
from app.obs.tracing import new_trace_id
from app.schemas import (
    ArtifactOut,
    CreateArtifactRequest,
    RetrievedChunk,
    RetrieveRequest,
    RetrieveResponse,
    UpdateArtifactRequest,
)
from app.services.retrieval import retrieve
from app.services.sanitize import prepare_artifact_content

router = APIRouter()


@router.post("/internal/retrieve", response_model=RetrieveResponse)
async def internal_retrieve(
    body: RetrieveRequest,
    x_internal_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RetrieveResponse:
    trace_id = new_trace_id()
    if x_internal_token != settings.agent_internal_token:
        raise ApiError(401, "UNAUTHORIZED", "missing or invalid internal token", trace_id=trace_id)

    result = await retrieve(db, settings, body.query, body.session_id, trace_id, k=body.k)
    return RetrieveResponse(
        abstained=result.abstained,
        floor=result.floor,
        chunks=[
            RetrievedChunk(
                chunk_id=c.chunk_id,
                episode=c.episode_title,
                guest=c.guest,
                youtube_url=c.youtube_url,
                start_seconds=c.start_seconds,
                rank=rank,
                score=round(c.score, 4),
                text=c.text,
            )
            for rank, c in enumerate(result.chunks, start=1)
        ],
    )


@router.post("/internal/artifacts", response_model=ArtifactOut, status_code=201)
async def internal_create_artifact(
    body: CreateArtifactRequest,
    x_internal_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ArtifactOut:
    trace_id = new_trace_id()
    if x_internal_token != settings.agent_internal_token:
        raise ApiError(401, "UNAUTHORIZED", "missing or invalid internal token", trace_id=trace_id)

    content, sanitized = prepare_artifact_content(body.kind, body.content, trace_id)
    row = ArtifactRow(
        session_id=body.session_id,
        message_id=body.message_id,
        kind=body.kind,
        title=body.title,
        content=content,
        sanitized=sanitized,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return ArtifactOut(
        id=row.id,
        session_id=row.session_id,
        message_id=row.message_id,
        kind=row.kind,
        title=row.title,
        content=row.content,
        sanitized=row.sanitized,
        created_at=row.created_at,
    )


@router.patch("/internal/artifacts/{artifact_id}", response_model=ArtifactOut)
async def internal_update_artifact(
    artifact_id: uuid.UUID,
    body: UpdateArtifactRequest,
    x_internal_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ArtifactOut:
    trace_id = new_trace_id()
    if x_internal_token != settings.agent_internal_token:
        raise ApiError(401, "UNAUTHORIZED", "missing or invalid internal token", trace_id=trace_id)

    row = await db.get(ArtifactRow, artifact_id)
    # session_id mismatch is treated the same as "doesn't exist" rather than
    # 403 — this internal surface never confirms an id exists in a session
    # the caller didn't already prove it belongs to.
    if row is None or row.session_id != body.session_id:
        raise not_found("artifact", trace_id)

    content, sanitized = prepare_artifact_content(row.kind, body.content, trace_id)
    row.content = content
    row.sanitized = sanitized
    if body.title is not None:
        row.title = body.title
    await db.commit()
    await db.refresh(row)
    return ArtifactOut(
        id=row.id,
        session_id=row.session_id,
        message_id=row.message_id,
        kind=row.kind,
        title=row.title,
        content=row.content,
        sanitized=row.sanitized,
        created_at=row.created_at,
    )
