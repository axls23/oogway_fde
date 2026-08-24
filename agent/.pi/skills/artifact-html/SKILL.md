---
name: artifact-html
description: >
  Produce a self-contained Markdown document or HTML/CSS snippet from the
  current conversation for the in-app Artifact Viewer. Use when the user
  asks for a document, one-pager, memo, or rendered snippet rather than a
  Ship 30 essay.
---

# Artifact generation skill

Output is rendered in a sandboxed `srcdoc` iframe with `sandbox="allow-scripts"`
and **no** `allow-same-origin`, under a CSP blocking all network egress
(architecture.md §7.6, ADR-004). Write as if every one of these constraints
is already enforced — because it is, server-side, regardless of what you
produce — but producing compliant output means the artifact actually works
instead of rendering broken or blocked.

## When asked for Markdown

- Return plain Markdown: headings, lists, tables, bold/italic, code fences.
  No raw HTML inside the Markdown — the renderer's sanitizer strips it, so
  including it wastes tokens.
- Ground factual claims the same way the chat does: name the guest and
  episode inline for anything sourced from retrieval.

## When asked for HTML

- Return ONE self-contained HTML fragment: inline `<style>`, no external
  `<link>` stylesheets, no external `<script src>`, no remote `<img src>`
  (use `data:` URIs or omit images) — any of these will simply fail to
  load under the CSP, so it produces a visibly broken artifact instead of
  a silent failure.
- Inline `<script>` tags are allowed and will execute, but in an opaque
  origin with no access to cookies, `localStorage`, or the parent page.
  Do not write scripts that assume they can `fetch()` anything — network
  is blocked entirely.
- No `<form>` submission, no top-level navigation (`window.location`,
  `target="_top"`), no `window.open` — all blocked by the sandbox.
- Keep total output under roughly 100KB. The viewer enforces a size cap;
  a truncated artifact is worse than a smaller complete one.

## Tool contract

Call `create_artifact` with `kind: "markdown" | "html"`, a short `title`,
and the full `content`. The tool response confirms persistence; you do not
need to repeat the content in your reply — summarize what you made in one
sentence and let the artifact pane show the rest.
