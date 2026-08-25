"""POST/GET /extension-proposals, PATCH /extension-proposals/{id}.

A review queue for user-drafted agent/.pi/extensions/ entries — NOT a
deployment path. Root CLAUDE.md invariant #4: the agent only ever loads
extensions listed in agent/.pi/extensions/manifest.json by exact path,
content sha256, and declared tool names (agent/src/capabilities.ts).
Nothing here writes to that file, that directory, or the agent's
filesystem at all. `status` transitions are bookkeeping for a human
maintainer; an 'approved' row still needs someone to commit the code,
add the matching manifest entry, and pass
tools/check_extension_manifest.py before it can ever run.
"""

from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExtensionProposal as ExtensionProposalRow
from app.db.session import get_db
from app.errors import not_found
from app.obs.tracing import new_trace_id
from app.schemas import (
    CreateExtensionProposalRequest,
    ExtensionProposalListResponse,
    ExtensionProposalOut,
    UpdateExtensionProposalStatusRequest,
)

router = APIRouter()


def _to_out(row: ExtensionProposalRow) -> ExtensionProposalOut:
    return ExtensionProposalOut(
        id=row.id,
        title=row.title,
        description=row.description,
        tool_names=row.tool_names,
        code=row.code,
        sha256=row.sha256,
        status=row.status,
        session_id=row.session_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/extension-proposals", response_model=ExtensionProposalOut, status_code=201)
async def create_extension_proposal(
    body: CreateExtensionProposalRequest,
    session_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> ExtensionProposalOut:
    sha256 = hashlib.sha256(body.code.encode("utf-8")).hexdigest()
    row = ExtensionProposalRow(
        title=body.title,
        description=body.description,
        tool_names=body.tool_names,
        code=body.code,
        sha256=sha256,
        session_id=session_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_out(row)


@router.get("/extension-proposals", response_model=ExtensionProposalListResponse)
async def list_extension_proposals(
    db: AsyncSession = Depends(get_db),
) -> ExtensionProposalListResponse:
    stmt = select(ExtensionProposalRow).order_by(ExtensionProposalRow.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return ExtensionProposalListResponse(items=[_to_out(r) for r in rows])


@router.patch("/extension-proposals/{proposal_id}", response_model=ExtensionProposalOut)
async def update_extension_proposal_status(
    proposal_id: uuid.UUID,
    body: UpdateExtensionProposalStatusRequest,
    db: AsyncSession = Depends(get_db),
) -> ExtensionProposalOut:
    trace_id = new_trace_id()
    row = await db.get(ExtensionProposalRow, proposal_id)
    if row is None:
        raise not_found("extension_proposal", trace_id)
    row.status = body.status
    await db.commit()
    await db.refresh(row)
    return _to_out(row)
