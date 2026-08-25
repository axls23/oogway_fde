"""Tests for services/sanitize.py: markdown allowlist cleaning, HTML size
cap + well-formedness, and the shared prepare_artifact_content() dispatcher.
"""

from __future__ import annotations

import pytest

from app.errors import ApiError
from app.services.sanitize import (
    MAX_ARTIFACT_BYTES,
    prepare_artifact_content,
    sanitize_markdown,
    validate_html,
)

TRACE = "test-trace"


def test_markdown_strips_script_tag() -> None:
    raw = "# Hello\n\n<script>alert('xss')</script>\n\nSome **bold** text."
    cleaned = sanitize_markdown(raw, TRACE)
    assert "<script>" not in cleaned
    assert "alert" not in cleaned or "<script" not in cleaned


def test_markdown_preserves_plain_markdown_syntax() -> None:
    raw = "# Heading\n\n- item one\n- item two\n\n**bold** and *em*"
    cleaned = sanitize_markdown(raw, TRACE)
    assert "# Heading" in cleaned
    assert "**bold**" in cleaned


def test_markdown_strips_javascript_href() -> None:
    raw = '<a href="javascript:alert(1)">click</a>'
    cleaned = sanitize_markdown(raw, TRACE)
    assert "javascript:" not in cleaned


def test_markdown_allows_allowlisted_tags() -> None:
    raw = "<p>Hello <strong>world</strong></p>"
    cleaned = sanitize_markdown(raw, TRACE)
    assert "<strong>" in cleaned
    assert "<p>" in cleaned


def test_markdown_over_size_cap_raises() -> None:
    huge = "a" * (MAX_ARTIFACT_BYTES + 1)
    with pytest.raises(ApiError) as exc_info:
        sanitize_markdown(huge, TRACE)
    assert exc_info.value.status_code == 413


def test_html_within_cap_and_well_formed_passes() -> None:
    validate_html("<html><body><h1>Hi</h1></body></html>", TRACE)  # no raise


def test_html_over_size_cap_raises() -> None:
    huge = "<div>" + "a" * MAX_ARTIFACT_BYTES + "</div>"
    with pytest.raises(ApiError) as exc_info:
        validate_html(huge, TRACE)
    assert exc_info.value.status_code == 413


def test_html_empty_raises() -> None:
    with pytest.raises(ApiError) as exc_info:
        validate_html("   ", TRACE)
    assert exc_info.value.code == "EMPTY_ARTIFACT"


def test_html_without_any_tag_raises() -> None:
    with pytest.raises(ApiError) as exc_info:
        validate_html("just some plain text, not a document", TRACE)
    assert exc_info.value.code == "MALFORMED_ARTIFACT"


def test_html_bare_fragment_passes() -> None:
    # artifact-html skill instructs a bare fragment, not a full <html>/<body>
    # document (the frontend supplies that wrapper) — see sanitize.py.
    validate_html(
        "<style>h2{color:red}</style><h2>Laura Schaffer's Insights</h2>"
        "<ul><li>Carve your own path</li></ul>",
        TRACE,
    )  # no raise


def test_html_is_stored_as_is_not_rewritten() -> None:
    # ADR-004: the iframe sandbox is the security boundary for HTML, not a
    # server-side rewriter. A <script> tag survives this module untouched.
    doc = "<html><body><script>fetch('https://example.com')</script></body></html>"
    content, sanitized = prepare_artifact_content("html", doc, TRACE)
    assert content == doc
    assert sanitized is False


def test_markdown_is_marked_sanitized() -> None:
    content, sanitized = prepare_artifact_content("markdown", "# hi", TRACE)
    assert sanitized is True
    assert "# hi" in content


def test_unknown_kind_raises() -> None:
    with pytest.raises(ApiError) as exc_info:
        prepare_artifact_content("pdf", "content", TRACE)
    assert exc_info.value.code == "INVALID_ARTIFACT_KIND"
