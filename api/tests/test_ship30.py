"""Unit tests for the deterministic parts of services/ship30.py: outline
parsing, assembly, and structural validation (AC7). These don't need a
model at all — that's the point of PRD §7.8: "quality guarantees must live
in code, not prompts." Full two-phase generation end-to-end against a real
agent is out of scope for tests/fixtures/fake_agent.py (kept deliberately
minimal per the task brief); see agent_client.py's module docstring for
the reconciliation point once the real agent service exists.
"""

from __future__ import annotations

import json

import pytest

from app.errors import ApiError
from app.services.ship30 import (
    MIN_HEADINGS,
    TARGET_WORDS,
    _assemble,
    _count_headings,
    _count_words,
    _parse_outline,
    _takeaway_heading,
    validate,
)

TRACE = "test-trace"


def test_parse_outline_happy_path() -> None:
    raw = json.dumps(
        {
            "hook_angle": "Most teams get onboarding backwards",
            "pattern": "lessons",
            "sections": [
                {"heading": "Lesson one", "chunk_ids": [1, 2]},
                {"heading": "Lesson two", "chunk_ids": [3]},
                {"heading": "Lesson three", "chunk_ids": [4, 999]},  # 999 not allowed
                {"heading": "Lesson four", "chunk_ids": []},
            ],
            "takeaway": "Ship the smallest onboarding step first.",
        }
    )
    outline = _parse_outline(raw, allowed_chunk_ids={1, 2, 3, 4}, trace_id=TRACE)
    assert outline.hook_angle == "Most teams get onboarding backwards"
    assert len(outline.sections) == 4
    assert outline.sections[2].chunk_ids == [4]  # 999 filtered out


def test_parse_outline_strips_markdown_code_fence() -> None:
    raw = "```json\n" + json.dumps(
        {
            "hook_angle": "h",
            "pattern": "steps",
            "sections": [{"heading": f"s{i}", "chunk_ids": []} for i in range(4)],
            "takeaway": "t",
        }
    ) + "\n```"
    outline = _parse_outline(raw, allowed_chunk_ids=set(), trace_id=TRACE)
    assert outline.pattern == "steps"


def test_parse_outline_rejects_invalid_json() -> None:
    with pytest.raises(ApiError) as exc_info:
        _parse_outline("not json at all", set(), TRACE)
    assert exc_info.value.code == "SHIP30_BAD_OUTLINE"


def test_parse_outline_rejects_wrong_section_count() -> None:
    raw = json.dumps(
        {
            "hook_angle": "h",
            "pattern": "steps",
            "sections": [{"heading": "only one", "chunk_ids": []}],
            "takeaway": "t",
        }
    )
    with pytest.raises(ApiError) as exc_info:
        _parse_outline(raw, set(), TRACE)
    assert exc_info.value.code == "SHIP30_BAD_OUTLINE"


def test_takeaway_heading_truncates_long_sentences() -> None:
    heading = _takeaway_heading("one two three four five six seven eight nine ten eleven twelve")
    assert len(heading.split()) == 10


def test_assemble_produces_h2_headings_and_hook_paragraph() -> None:
    doc = _assemble("A hook paragraph.", [("First Section", "Some prose here.")])
    assert doc.startswith("A hook paragraph.")
    assert "## First Section" in doc
    assert "Some prose here." in doc


def test_count_words_and_headings() -> None:
    doc = "hook words here\n\n## Heading One\n\nbody text\n\n## Heading Two\n\nmore body"
    assert _count_headings(doc) == 2
    assert _count_words(doc) == 13  # includes the two "##" tokens themselves


def test_validate_passes_within_tolerance() -> None:
    word = "lorem "
    body = word * (TARGET_WORDS // 6)  # roughly on target once split into "words"
    sections = [(f"H{i}", "word " * 30) for i in range(5)]
    doc = "\n".join([body] + [f"## {h}\n{p}" for h, p in sections])
    report = validate(doc, sections, distinct_sources=3)
    assert report.heading_count == 5
    assert report.distinct_sources == 3
    assert not report.empty_sections


def test_validate_flags_word_count_out_of_range() -> None:
    sections = [(f"H{i}", "word") for i in range(4)]
    doc = "short doc\n" + "\n".join(f"## {h}\n{p}" for h, p in sections)
    report = validate(doc, sections, distinct_sources=3)
    assert not report.ok
    assert any("word_count" in e for e in report.errors)


def test_validate_flags_too_few_headings() -> None:
    doc = "a" * TARGET_WORDS  # single blob, no headings at all — not realistic but isolates the check
    report = validate(doc, sections=[], distinct_sources=3)
    assert report.heading_count < MIN_HEADINGS
    assert not report.ok


def test_validate_flags_too_few_distinct_sources() -> None:
    sections = [(f"H{i}", "word " * 50) for i in range(5)]
    doc = "\n".join(f"## {h}\n{p}" for h, p in sections) + " " + "word " * (TARGET_WORDS - 250)
    report = validate(doc, sections, distinct_sources=1)
    assert not report.ok
    assert any("distinct_sources" in e for e in report.errors)


def test_validate_flags_empty_sections() -> None:
    sections = [("H1", "word " * 50), ("H2", "")]
    doc = "\n".join(f"## {h}\n{p}" for h, p in sections) + " " + "word " * (TARGET_WORDS - 50)
    report = validate(doc, sections, distinct_sources=3)
    assert not report.ok
    assert "H2" in report.empty_sections
