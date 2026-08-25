"""Pydantic request/response models derived from ``contracts/openapi.yaml``.

Field-for-field. If a field here doesn't exist in openapi.yaml, or a
required field in openapi.yaml is missing here, that's a contract drift bug
— fix this file to match the contract, never the reverse.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ErrorDetail(BaseModel):
    code: str
    message: str
    trace_id: str
    retryable: bool


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class SessionOut(BaseModel):
    id: uuid.UUID
    title: str | None
    provider: str
    model: str
    # NULL = every discovered skill active for this session (default). See
    # UpdateSessionCapabilitiesRequest below.
    enabled_skills: list[str] | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class CreateSessionRequest(BaseModel):
    title: str | None = None


class SessionListResponse(BaseModel):
    items: list[SessionOut]
    total: int


class CitationOut(BaseModel):
    chunk_id: int
    episode: str
    guest: str
    youtube_url: str | None
    start_seconds: int | None = None
    rank: int = Field(ge=1)
    score: float


class MessageOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: Literal["user", "assistant", "system"]
    content: str
    rewritten_query: str | None = None
    trace_id: str
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    abstained: bool
    created_at: dt.datetime
    citations: list[CitationOut] = Field(default_factory=list)


class SessionDetailOut(SessionOut):
    messages: list[MessageOut]


class PostMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class UpdateSessionCapabilitiesRequest(BaseModel):
    """PATCH /sessions/{id}/capabilities. `enabled_skills: null` resets to
    "every discovered skill active" (the default); `[]` disables all skills
    for this session; a non-empty list allowlists those names. Skill names
    are matched against what GET /config's capabilities.skills reports —
    an unknown name simply matches nothing (skills carry no tools, so this
    can never grant new model capability, only narrow prompt content)."""

    enabled_skills: list[str] | None = None


class EpisodeRef(BaseModel):
    id: int
    guest: str
    title: str
    youtube_url: str | None
    publish_date: dt.date | None = None
    source_path: str


class ChunkDetailOut(BaseModel):
    id: int
    text: str
    ordinal: int | None = None
    episode: EpisodeRef
    start_seconds: int | None = None


class ArtifactOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    message_id: uuid.UUID | None = None
    kind: Literal["markdown", "html"]
    title: str | None = None
    content: str
    sanitized: bool
    created_at: dt.datetime


class CreateArtifactRequest(BaseModel):
    session_id: uuid.UUID
    message_id: uuid.UUID | None = None
    kind: Literal["markdown", "html"]
    title: str | None = None
    content: str = Field(min_length=1, max_length=120_000)


class UpdateArtifactRequest(BaseModel):
    """No `kind` — edit_artifact revises content/title on an existing row,
    never its kind (contracts/openapi.yaml)."""

    session_id: uuid.UUID
    title: str | None = None
    content: str = Field(min_length=1, max_length=120_000)


class CorpusStats(BaseModel):
    episode_count: int
    chunk_count: int


class SkillOut(BaseModel):
    name: str
    description: str


class ExtensionOut(BaseModel):
    path: str
    tools: list[str]


class CapabilitiesOut(BaseModel):
    """Root CLAUDE.md invariant #4 / architecture.md §8.5: what's actually
    active on the agent right now, for the UI capabilities panel. See
    agent/src/capabilities.ts for how this is computed and gated."""

    skills: list[SkillOut]
    extensions: list[ExtensionOut]
    extensions_enabled: bool
    tools: list[str]
    agent_reachable: bool


_TOOL_NAME_RE = r"^[a-z][a-z0-9_]{0,63}$"


class CreateExtensionProposalRequest(BaseModel):
    """A user-drafted proposal for a new agent/.pi/extensions/ entry.

    This never deploys anything (root CLAUDE.md invariant #4). It's a
    review-queue row: a maintainer must still copy `code` into a committed
    file, add a matching agent/.pi/extensions/manifest.json entry (path,
    sha256, tools, approvedBy), and pass tools/check_extension_manifest.py
    before it can ever run. See agent/src/capabilities.ts.
    """

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    tool_names: list[str] = Field(min_length=1, max_length=20)
    code: str = Field(min_length=1, max_length=100_000)

    @field_validator("tool_names")
    @classmethod
    def _validate_tool_names(cls, v: list[str]) -> list[str]:
        for name in v:
            if not re.match(_TOOL_NAME_RE, name):
                raise ValueError(f"tool name {name!r} must match {_TOOL_NAME_RE}")
        return v


class ExtensionProposalOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    tool_names: list[str]
    code: str
    sha256: str
    status: Literal["pending", "approved", "rejected"]
    session_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime


class ExtensionProposalListResponse(BaseModel):
    items: list[ExtensionProposalOut]


class UpdateExtensionProposalStatusRequest(BaseModel):
    status: Literal["pending", "approved", "rejected"]


class ConfigResponse(BaseModel):
    provider: Literal["ollama", "anthropic"]
    model: str
    cloud_available: bool
    corpus: CorpusStats
    capabilities: CapabilitiesOut


DepStatus = Literal["ok", "degraded", "down"]


class HealthDeps(BaseModel):
    db: DepStatus
    ollama: DepStatus
    agent: DepStatus


class RetrieveRequest(BaseModel):
    query: str
    session_id: uuid.UUID
    k: int = 8


class RetrievedChunk(CitationOut):
    text: str


class RetrieveResponse(BaseModel):
    abstained: bool
    floor: float | None = None
    chunks: list[RetrievedChunk]
