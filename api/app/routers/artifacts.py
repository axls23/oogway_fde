"""GET /artifacts/{id}, GET /chunks/{id}.

/chunks/{id} serves flow F2 (provenance check): clicking a citation chip
expands the verbatim retrieved snippet with NO second model call — this
handler does exactly one indexed read (chunks joined to episodes), nothing
else (AC5).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artifact, Chunk, Episode
from app.db.session import get_db
from app.errors import not_found
from app.obs.tracing import new_trace_id
from app.schemas import ArtifactOut, ChunkDetailOut, EpisodeRef

router = APIRouter()


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(artifact_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ArtifactOut:
    trace_id = new_trace_id()
    row = await db.get(Artifact, artifact_id)
    if row is None:
        raise not_found("artifact", trace_id)
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


@router.get("/chunks/{chunk_id}", response_model=ChunkDetailOut)
async def get_chunk(chunk_id: int, db: AsyncSession = Depends(get_db)) -> ChunkDetailOut:
    trace_id = new_trace_id()
    stmt = select(Chunk, Episode).join(Episode, Episode.id == Chunk.episode_id).where(
        Chunk.id == chunk_id
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise not_found("chunk", trace_id)
    chunk, episode = row
    return ChunkDetailOut(
        id=chunk.id,
        text=chunk.text,
        ordinal=chunk.ordinal,
        start_seconds=chunk.start_seconds,
        episode=EpisodeRef(
            id=episode.id,
            guest=episode.guest,
            title=episode.title,
            youtube_url=episode.youtube_url,
            publish_date=episode.publish_date,
            source_path=episode.source_path,
        ),
    )
