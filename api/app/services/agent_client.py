"""HTTP+NDJSON client to the `agent` service (Node + Pi SDK, architecture.md §8).

======================================================================
RECONCILED AGENT-SERVICE INTERFACE — matches agent/src/server.ts + wire-types.ts
======================================================================
  POST {AGENT_BASE_URL}/turn
  Request body (JSON):
    {
      "trace_id": str,
      "session_id": str,
      "messages": [{"role": "user"|"assistant"|"system", "content": str}, ...]
        # FULL rehydrated history including the new trailing user turn
        # (agent/src/session.ts: ADR-002, this service is stateless and
        # takes no provider/model/context_chunks/system_prompt fields —
        # provider+model come from its own LLM_PROVIDER/LLM_MODEL env
        # [docker-compose.yml gives api and agent the same env], the system
        # prompt is fixed server-side, and retrieval context is fetched by
        # the agent's own search_transcripts tool call against
        # POST /internal/retrieve rather than being handed pre-fetched
        # here — see routers/internal.py's module docstring.
      "enabled_skills": [str, ...] | omitted
        # Optional per-session skill allowlist (root CLAUDE.md invariant
        # #4). Omitted -> every discovered skill active (default).
    }
  Response: streamed newline-delimited JSON, one event object per line
  (Content-Type application/x-ndjson; NOT SSE `event:`/`data:` framing),
  each with at least a "type" field (agent/src/wire-types.ts WireEvent):
    {"type": "stage", "stage": "thinking|retrieving|drafting|outlining|assembling",
     "detail": str|null}
    {"type": "token", "delta": str}
    {"type": "citation", "chunks": [
        {"chunk_id": int, "episode": str, "guest": str, "youtube_url": str|null,
         "start_seconds": int|null, "rank": int, "score": float}, ...
     ]}   # ALL chunks from one search_transcripts call batched into one
          # frame — api fans this out into one sse.citation_frame per chunk.
    {"type": "artifact", "artifact_id": str, "kind": "markdown|html", "title": str}
        # no `content` — the agent's create_artifact tool already persisted
        # it via POST /internal/artifacts before emitting this event.
    {"type": "error", "code": str, "message": str, "retryable": bool, "partial": bool}
    {"type": "done", "latency_ms": int}
        # no `message_id`/`abstained` — this service never writes to
        # Postgres and doesn't decide abstention (api's retrieval-floor
        # guard, root CLAUDE.md invariant #2); api fills both in itself
        # when it builds the real SSE `done` frame.

  A non-200 response (400/500/503) is a JSON ErrorEnvelope-shaped body
  emitted before any streaming started; httpx's raise_for_status() below
  turns that into agent_unreachable().

  GET {AGENT_BASE_URL}/healthz -> 200 {"status": "ok"} when reachable.

WHY CITATIONS DON'T PRIMARILY COME FROM THIS CLIENT: root CLAUDE.md
invariant 1 says citations are built from retrieval metadata, never parsed
from model output. Concretely: `services/retrieval.py` already ran BEFORE
this client is ever called for the primary F1 turn (see services/turn.py),
so the citation SSE frames/CitationRows for that primary retrieval are
built directly from that RetrieveResult, not from anything this client
returns. A `citation` event this client does see (the agent independently
re-querying mid-turn, per routers/internal.py) is *also* built from
retrieval metadata — the same /internal/retrieve endpoint — so surfacing it
as additional citations does not violate the invariant; see
services/turn.py's `_run_agent` for how the two are merged and deduped.
======================================================================
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from app.config import Settings
from app.errors import agent_unreachable
from app.obs.logging import log_event
from app.services.provider import assert_provider_ready

EventType = Literal["stage", "token", "citation", "artifact", "error", "done"]
_KNOWN_EVENT_TYPES = ("stage", "token", "citation", "artifact", "error", "done")


@dataclass
class AgentEvent:
    type: EventType
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_event(line: str) -> AgentEvent | None:
    line = line.strip()
    if not line:
        return None
    obj = json.loads(line)
    event_type = obj.get("type")
    if event_type not in _KNOWN_EVENT_TYPES:
        return None
    return AgentEvent(type=event_type, raw=obj)


async def stream_turn(
    settings: Settings,
    trace_id: str,
    session_id: str,
    history: list[dict[str, str]],
    message: str,
    *,
    enabled_skills: list[str] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Stream normalized events from the agent's POST /turn.

    `history` excludes the new turn; `message` is appended as the trailing
    user-role entry, matching agent/src/session.ts's `rehydrate()`, which
    requires the message list to end with a user message.

    `enabled_skills`, when not None, is this session's skill allowlist
    (root CLAUDE.md invariant #4 — skills carry no tools, so this can only
    narrow prompt content, never grant new capability). Omitted entirely
    when None so the agent's default ("every skill active") applies.

    Raises ApiError(503) if the agent is unreachable or the configured
    provider has no credentials (ADR-005: fail loudly, never fail over).
    """
    assert_provider_ready(settings, trace_id)

    messages = [*history, {"role": "user", "content": message}]
    body: dict[str, Any] = {
        "trace_id": trace_id,
        "session_id": session_id,
        "messages": messages,
    }
    if enabled_skills is not None:
        body["enabled_skills"] = enabled_skills
    url = f"{settings.agent_base_url.rstrip('/')}/turn"
    try:
        async with httpx.AsyncClient(timeout=settings.model_timeout_s) as client, client.stream(
            "POST", url, json=body, headers={"X-Trace-Id": trace_id}
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                event = _parse_event(line)
                if event is None:
                    continue
                if event.type == "citation":
                    log_event(
                        "agent_citation_observed",
                        trace_id,
                        chunk_count=len(event.raw.get("chunks", [])),
                    )
                yield event
    except httpx.HTTPError as exc:
        log_event("agent_call_failed", trace_id, level=40, error=str(exc), url=url)
        raise agent_unreachable(trace_id, detail=str(exc)) from exc


async def collect_turn_text(
    settings: Settings,
    trace_id: str,
    session_id: str,
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Drain a full non-interactive turn (used by ship30.py's outline/section
    calls, which assemble deterministically in Python rather than streaming
    to the client) and return the concatenated token content."""
    parts: list[str] = []
    async for event in stream_turn(
        settings,
        trace_id,
        session_id,
        history or [],
        message,
    ):
        if event.type == "token":
            parts.append(str(event.raw.get("delta", "")))
        elif event.type == "error":
            log_event(
                "agent_turn_error_event",
                trace_id,
                level=40,
                code=event.raw.get("code"),
                message=event.raw.get("message"),
            )
    return "".join(parts)


async def check_health(settings: Settings) -> bool:
    url = f"{settings.agent_base_url.rstrip('/')}/healthz"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
