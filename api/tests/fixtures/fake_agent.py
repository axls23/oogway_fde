"""Stub `agent` service speaking the real agent/src/server.ts wire protocol
(see app/services/agent_client.py's module docstring for the reconciled
shape).

Not the real Pi-backed service — just enough NDJSON-over-HTTP to let api/'s
integration tests exercise the SSE-frame-emitting path without requiring
the Node agent service to be running. Run standalone with
`uvicorn tests.fixtures.fake_agent:app --port 8100`, or mount directly via
`httpx.ASGITransport(app=app)` in tests for a socket-free run.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/turn")
async def turn(request: Request) -> StreamingResponse:
    body = await request.json()
    messages = body.get("messages", [])
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")

    # Two test-only sentinels, parsed out of the last user message, that let
    # api/tests exercise turn.py's artifact-history plumbing without a real
    # Pi-backed agent process actually calling create_artifact/edit_artifact:
    #   "__create_artifact__:{artifact_id}" -> emit an `artifact` event for
    #     an artifact the test already created directly via
    #     POST /internal/artifacts (simulating "the tool already ran").
    #   "__echo_history__" -> stream back every message's content, joined,
    #     so a test can assert on exactly what api sent this turn (in
    #     particular, whether the artifact note from turn.py is present).
    artifact_id: str | None = None
    if last_user.startswith("__create_artifact__:"):
        artifact_id = last_user.split(":", 1)[1]

    async def events() -> AsyncIterator[bytes]:
        yield json.dumps({"type": "stage", "stage": "thinking", "detail": None}).encode() + b"\n"
        yield json.dumps({"type": "stage", "stage": "drafting", "detail": None}).encode() + b"\n"
        if artifact_id:
            artifact_event = {
                "type": "artifact",
                "artifact_id": artifact_id,
                "kind": "markdown",
                "title": "Test Artifact",
            }
            yield json.dumps(artifact_event).encode() + b"\n"
            for word in "Made you an artifact.".split():
                yield json.dumps({"type": "token", "delta": word + " "}).encode() + b"\n"
        elif last_user == "__echo_history__":
            joined = " ||| ".join(f"{m.get('role')}:{m.get('content')}" for m in messages)
            for word in joined.split(" "):
                yield json.dumps({"type": "token", "delta": word + " "}).encode() + b"\n"
        else:
            for word in f"Fake answer about: {last_user}".split():
                yield json.dumps({"type": "token", "delta": word + " "}).encode() + b"\n"
        yield json.dumps({"type": "done", "latency_ms": 12}).encode() + b"\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")
