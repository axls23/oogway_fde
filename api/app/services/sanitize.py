"""Artifact persistence prep: markdown sanitization + size/well-formedness checks.

Two different content kinds, two different jobs (ADR-004, architecture.md
§10, PRD §7.6):

- **markdown**: run through `bleach` with an allowlisted tag/attribute set
  before persisting. No raw HTML passthrough — a model that tries to smuggle
  `<script>` into a markdown artifact gets it stripped server-side. Stored
  with `sanitized=True`.
- **html**: persisted as-is. The iframe (`sandbox="allow-scripts"`, no
  `allow-same-origin`, restrictive CSP, no network egress) IS the
  sanitization boundary per ADR-004 — that's a frontend/browser control,
  not something a server-side HTML rewriter can substitute for without
  risking a false sense of safety (a rewriter can be bypassed; an opaque
  sandboxed origin cannot). This module's job for html is only: enforce the
  size cap and a basic well-formedness check, not rewrite the markup.
  Stored with `sanitized=False`.
"""

from __future__ import annotations

import re

import bleach

from app.errors import ApiError

_TAG_RE = re.compile(r"<[a-zA-Z][a-zA-Z0-9-]*[\s>/]")

MAX_ARTIFACT_BYTES = 100_000

ALLOWED_TAGS = [
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "b", "i", "u", "s", "del",
    "ul", "ol", "li",
    "blockquote", "pre", "code",
    "a", "img",
    "table", "thead", "tbody", "tr", "th", "td",
]
ALLOWED_ATTRS = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
}
ALLOWED_PROTOCOLS = ["http", "https", "data"]


def _check_size(content: str, trace_id: str) -> None:
    size = len(content.encode("utf-8"))
    if size > MAX_ARTIFACT_BYTES:
        raise ApiError(
            413,
            "ARTIFACT_TOO_LARGE",
            f"artifact content is {size} bytes, exceeds the {MAX_ARTIFACT_BYTES}-byte cap",
            trace_id=trace_id,
        )


def sanitize_markdown(content: str, trace_id: str) -> str:
    """Bleach-clean any raw HTML embedded in markdown source. Markdown syntax
    itself (#, **, -, etc.) is untouched — bleach only acts on HTML tags."""
    _check_size(content, trace_id)
    return bleach.clean(
        content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )


def validate_html(content: str, trace_id: str) -> None:
    """Size cap + minimal well-formedness check. Does NOT rewrite markup —
    see module docstring for why that's deliberately not this module's job.

    The artifact-html skill (agent/.pi/skills/artifact-html/SKILL.md) tells
    the model to return a bare self-contained fragment, not a full document
    with an <html>/<body> wrapper — the frontend (sandboxHtml.ts) supplies
    that wrapper itself before rendering. So this only checks for *some*
    HTML tag, not a specific root element; requiring html/body/div rejected
    valid fragments like "<style>...</style><h2>...</h2><ul>...</ul>".
    """
    _check_size(content, trace_id)
    stripped = content.strip()
    if not stripped:
        raise ApiError(422, "EMPTY_ARTIFACT", "html artifact content is empty", trace_id=trace_id)
    if not _TAG_RE.search(stripped):
        raise ApiError(
            422,
            "MALFORMED_ARTIFACT",
            "html artifact does not contain any HTML tags",
            trace_id=trace_id,
        )


def prepare_artifact_content(
    kind: str, content: str, trace_id: str
) -> tuple[str, bool]:
    """Returns (content_to_persist, sanitized_flag)."""
    if kind == "markdown":
        return sanitize_markdown(content, trace_id), True
    if kind == "html":
        validate_html(content, trace_id)
        return content, False
    raise ApiError(
        422, "INVALID_ARTIFACT_KIND", f"unknown artifact kind {kind!r}", trace_id=trace_id
    )
