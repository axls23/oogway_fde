"""Validate every SSE frame builder's output against
contracts/sse-frames.schema.json directly with jsonschema — not just by
eyeballing (api/CLAUDE.md non-negotiable behavior).
"""

from __future__ import annotations

import json
import os

import jsonschema
import pytest

from app.services import sse_frames as sse

_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "contracts", "sse-frames.schema.json"
)


def _load_schema() -> dict[str, object]:
    with open(_SCHEMA_PATH) as f:
        return json.load(f)  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def schema() -> dict[str, object]:
    if not os.path.exists(_SCHEMA_PATH):
        pytest.skip(f"contracts/sse-frames.schema.json not found at {_SCHEMA_PATH}")
    return _load_schema()


def _validate(frame: str, schema: dict[str, object]) -> None:
    parsed = sse.frame_to_dict(frame)
    jsonschema.validate(instance=parsed, schema=schema)


def test_stage_frame_validates(schema: dict[str, object]) -> None:
    _validate(sse.stage_frame("retrieving"), schema)
    _validate(sse.stage_frame("drafting", "section 3 of 6"), schema)


def test_stage_frame_rejects_bad_stage_name(schema: dict[str, object]) -> None:
    bad = sse.stage_frame("thinking")
    parsed = sse.frame_to_dict(bad)
    parsed["data"]["stage"] = "not-a-real-stage"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=parsed, schema=schema)


def test_token_frame_validates(schema: dict[str, object]) -> None:
    _validate(sse.token_frame("Product-market fit is"), schema)


def test_citation_frame_validates(schema: dict[str, object]) -> None:
    _validate(sse.citation_frame(8412, "Some Episode", "Some Guest", 1, 0.71), schema)


def test_artifact_frame_validates(schema: dict[str, object]) -> None:
    import uuid

    _validate(sse.artifact_frame(str(uuid.uuid4()), "html", "My Artifact"), schema)


def test_error_frame_validates_with_and_without_partial(schema: dict[str, object]) -> None:
    _validate(sse.error_frame("MODEL_TIMEOUT", "timed out", True, partial=True), schema)
    _validate(sse.error_frame("OLLAMA_UNREACHABLE", "down", True), schema)


def test_done_frame_validates(schema: dict[str, object]) -> None:
    import uuid

    _validate(sse.done_frame(str(uuid.uuid4()), 2140, False), schema)


def test_frame_wire_format_has_event_and_data_lines() -> None:
    frame = sse.token_frame("hello")
    assert frame.startswith("event: token\n")
    assert "data: " in frame
    assert frame.endswith("\n\n")
