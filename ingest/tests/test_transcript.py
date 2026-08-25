"""Tests for transcript.py: frontmatter parsing + speaker-turn parsing,
including start_seconds extraction, against real transcript excerpts copied
from the corpus (see tests/fixtures/*.md) and hand-built malformed cases."""

from __future__ import annotations

import pytest
from conftest import FIXTURES_DIR

from transcript import (
    MalformedTranscriptError,
    content_hash,
    parse_frontmatter,
    parse_turns,
    split_frontmatter_and_body,
)


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ─── Frontmatter parsing ─────────────────────────────────────────────────


def test_parse_frontmatter_dominant_format():
    raw = _load("dominant_format_excerpt.md")
    fm = parse_frontmatter(raw)
    assert fm.guest == "Ada Chen Rekhi"
    # YAML folded scalar across two lines collapses to a single space-joined string.
    assert fm.title == "Feeling stuck? Here's how to know when it's time to leave your job | Ada Chen Rekhi"
    assert fm.youtube_url == "https://www.youtube.com/watch?v=l-T8sNRcWQk"
    assert fm.video_id == "l-T8sNRcWQk"
    assert fm.publish_date == "2023-04-21"
    assert fm.duration_seconds == 230


def test_parse_frontmatter_missing_frontmatter_block_raises():
    raw = _load("malformed_no_frontmatter.md")
    with pytest.raises(MalformedTranscriptError):
        parse_frontmatter(raw)


def test_parse_frontmatter_bad_yaml_raises():
    raw = _load("malformed_bad_yaml.md")
    with pytest.raises(MalformedTranscriptError):
        parse_frontmatter(raw)


def test_parse_frontmatter_missing_title_raises():
    raw = _load("malformed_missing_title.md")
    with pytest.raises(MalformedTranscriptError):
        parse_frontmatter(raw)


def test_parse_frontmatter_empty_string_fields_become_none():
    raw = """---
guest: Someone
title: Some Title
youtube_url: ''
video_id: ''
---

# Some Title

## Transcript

Someone (00:00:00):
Text.
"""
    fm = parse_frontmatter(raw)
    assert fm.youtube_url is None
    assert fm.video_id is None


# ─── Turn parsing / start_seconds extraction ────────────────────────────


def test_parse_turns_dominant_format_extracts_speakers_and_timestamps():
    raw = _load("dominant_format_excerpt.md")
    body = split_frontmatter_and_body(raw)
    turns = parse_turns(body)

    assert len(turns) == 3
    assert turns[0].speaker == "Ada Chen Rekhi"
    assert turns[0].start_seconds == 0
    assert "terrible outcome" in turns[0].text

    assert turns[1].speaker == "Lenny"
    assert turns[1].start_seconds == 36  # 00:00:36

    # Continuation line "(00:01:21):" has no speaker name -- must carry
    # forward the most recently named speaker (Lenny).
    assert turns[2].speaker == "Lenny"
    assert turns[2].start_seconds == 81  # 00:01:21


def test_parse_turns_mmss_format():
    raw = _load("mmss_format_excerpt.md")
    body = split_frontmatter_and_body(raw)
    turns = parse_turns(body)

    assert len(turns) == 4
    assert turns[0].speaker == "Lenny Rachitsky"
    assert turns[0].start_seconds == 0
    assert turns[1].speaker == "Asha Sharma"
    assert turns[1].start_seconds == 4
    assert turns[2].start_seconds == 23
    assert turns[3].start_seconds == 29


def test_parse_turns_inline_bracket_fallback_format():
    raw = _load("inline_bracket_format_excerpt.md")
    body = split_frontmatter_and_body(raw)
    turns = parse_turns(body)

    assert len(turns) == 3
    assert turns[0].speaker == "Ryan"
    assert turns[0].start_seconds == 0
    assert turns[1].speaker == "Lenny"
    assert turns[1].start_seconds == 28
    assert turns[2].speaker == "Ryan"
    assert turns[2].start_seconds == 52


def test_parse_turns_no_timestamp_fallback_format():
    raw = _load("no_timestamp_format_excerpt.md")
    body = split_frontmatter_and_body(raw)
    turns = parse_turns(body)

    assert len(turns) == 3
    assert turns[0].speaker == "Adriel Frederick"
    assert turns[0].start_seconds is None
    assert turns[1].speaker == "Lenny"
    assert turns[1].start_seconds is None


def test_parse_turns_empty_body_raises():
    with pytest.raises(MalformedTranscriptError):
        parse_turns("   \n\n  ")


def test_parse_turns_no_markers_raises():
    with pytest.raises(MalformedTranscriptError):
        parse_turns("Just some prose with no speaker markers at all.\n\nMore prose.")


def test_malformed_empty_body_end_to_end():
    raw = _load("malformed_empty_body.md")
    body = split_frontmatter_and_body(raw)
    with pytest.raises(MalformedTranscriptError):
        parse_turns(body)


# ─── content_hash ────────────────────────────────────────────────────────


def test_content_hash_is_deterministic_and_sensitive_to_change():
    a = content_hash(b"hello world")
    b = content_hash(b"hello world")
    c = content_hash(b"hello world!")
    assert a == b
    assert a != c
    assert len(a) == 64  # sha256 hex digest
