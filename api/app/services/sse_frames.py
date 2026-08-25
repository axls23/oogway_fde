"""Builders for the SSE frame shapes in contracts/sse-frames.schema.json.

Every frame this service emits over `/sessions/{id}/messages` goes through
one of these functions, so there is exactly one place that knows the wire
format. tests/test_sse_frames.py validates the output of each builder
against the JSON Schema directly (not just by eyeballing — api/CLAUDE.md).
"""

from __future__ import annotations

import json
from typing import Any, Literal

StageName = Literal["thinking", "retrieving", "drafting", "outlining", "assembling"]


def _frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stage_frame(stage: StageName, detail: str | None = None) -> str:
    return _frame("stage", {"stage": stage, "detail": detail})


def token_frame(text: str) -> str:
    return _frame("token", {"text": text})


def citation_frame(chunk_id: int, episode: str, guest: str, rank: int, score: float) -> str:
    return _frame(
        "citation",
        {"chunk_id": chunk_id, "episode": episode, "guest": guest, "rank": rank, "score": score},
    )


def artifact_frame(artifact_id: str, kind: Literal["markdown", "html"], title: str) -> str:
    return _frame("artifact", {"artifact_id": artifact_id, "kind": kind, "title": title})


def error_frame(
    code: str, message: str, retryable: bool, partial: bool | None = None
) -> str:
    data: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    if partial is not None:
        data["partial"] = partial
    return _frame("error", data)


def done_frame(message_id: str, latency_ms: int, abstained: bool) -> str:
    return _frame(
        "done", {"message_id": message_id, "latency_ms": latency_ms, "abstained": abstained}
    )


def frame_to_dict(frame: str) -> dict[str, Any]:
    """Parse one emitted frame back into {"event":..., "data": {...}} for
    schema validation in tests."""
    lines = [line for line in frame.strip("\n").split("\n") if line]
    event_line = next(line for line in lines if line.startswith("event: "))
    data_line = next(line for line in lines if line.startswith("data: "))
    return {
        "event": event_line[len("event: ") :],
        "data": json.loads(data_line[len("data: ") :]),
    }
