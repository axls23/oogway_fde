# Manual UI test plan

Automated tests cover API contracts, retrieval, routing, and persistence
(`api/tests/`, `agent/`'s test suite, `tests/eval/`). This plan covers what
those can't: what the UI actually looks and feels like. Run against
`make up` on the local Ollama path unless a row says otherwise.

## 1. Cold start (F6)

- [ ] `make corpus && make up` on a clean checkout with `.env` copied from
      `.env.example` (no edits). Time it — should be well under 10 minutes
      including model pulls if not cached (AC1).
- [ ] UI opens to an empty session with three starter prompts, each
      demonstrating a different capability.
- [ ] Provider badge reads `● ollama · qwen2.5:7b-instruct` on load, sourced
      from `GET /config`.

## 2. Grounded Q&A with follow-ups (F1, AC4)

- [ ] Ask an in-corpus question from `tests/eval/questions.yaml`. Response
      streams token-by-token (not all-at-once). A "retrieving" status chip
      appears and clears before tokens start.
- [ ] Citation chips appear beneath the answer, guest + episode title
      visible, arriving progressively rather than all at the end.
- [ ] Ask a pronominal follow-up ("what about B2B?"). Confirm the answer
      stays on-topic — inspect the `rewritten_query` in `api` logs
      (`trace_id` grep) to confirm condensation actually ran.
- [ ] Ask "expand on that." Same check.
- [ ] Start a second, unrelated question in the same session — confirm the
      system doesn't over-anchor on the earlier topic (session boost is
      capped, not absolute).

## 3. Citation expand / provenance (F2, AC5)

- [ ] Click a citation chip. It expands inline (accordion, not a modal),
      chat scroll position is preserved.
- [ ] Open the browser network panel first — confirm expanding a citation
      fires **zero** new network requests (data already arrived with the
      message).
- [ ] Click again — collapses.
- [ ] Keyboard: Tab to a citation chip, expand with Enter/Space,
      `aria-expanded` reflects state (inspect via devtools accessibility
      tree or a screen reader).

## 4. Corpus miss / abstention (F5, AC3)

- [ ] Ask an out-of-corpus question from `tests/eval/questions.yaml`.
      Response is a visually distinct **neutral** card (not styled as an
      error) naming the gap and suggesting adjacent indexed topics.
- [ ] Confirm this doesn't read as a crash or a red error state — color is
      not the only signal distinguishing it from a real error.

## 5. Ship 30 essay (F3, AC7)

- [ ] Ask for an essay on the current thread's topic. Artifact pane opens
      immediately (not after a delay).
- [ ] Staged progress is visible and updates in place: retrieving →
      outlining → drafting section N of M → assembling. No silent gap of
      more than a few seconds without a visible state change.
- [ ] Result lands in the Artifact Viewer, Preview tab active. Roughly
      1,250 words, ≥4 headings, inline citations to named guests/episodes.
- [ ] Repeat 2 more times (fresh sessions) — structure should hold across
      runs (word count, heading count) even though prose varies.

## 6. Artifact generation and sandbox (F4, AC8)

- [ ] Ask for an HTML one-pager. Confirm it renders in the iframe pane.
- [ ] Ask for (or manually craft a follow-up requesting) an artifact that
      includes `<script>fetch('https://example.com')</script>`. Open the
      browser network panel — confirm the request never fires.
- [ ] Confirm the iframe has a visible "sandboxed" label distinguishing it
      from trusted app chrome.
- [ ] Toggle Preview/Source — Source shows raw HTML, unrendered.
- [ ] Copy button copies raw source (paste into a text editor to check);
      Download saves a `.html` file that opens standalone in a browser
      (still sandboxed by nothing once downloaded — that's expected, the
      sandbox is a viewer property, not a file property).
- [ ] Ask for a Markdown document instead — confirm it renders through the
      sanitized markdown path, not raw HTML passthrough (try asking it to
      include a raw `<img onerror=...>` tag; confirm it's stripped or
      escaped, not executed).

## 7. Provider toggle and failure modes (AC9, AC10)

- [ ] Stop Ollama (`pkill ollama` or however it's running). Send a message.
      UI shows a named error banner ("Ollama unreachable" or similar,
      explicit), a Retry action, and explicitly does **not** silently
      switch to a cloud response — verify no cloud request appears in
      `api` logs.
- [ ] Restart Ollama, click Retry — turn succeeds.
- [ ] Edit `.env` to `LLM_PROVIDER=anthropic` with a valid
      `ANTHROPIC_API_KEY`, restart `api`/`agent`. Provider badge updates
      to `● anthropic · claude-sonnet-4-5` without any frontend code
      change.
- [ ] With `LLM_PROVIDER=anthropic` and NO `ANTHROPIC_API_KEY` set, confirm
      the app still starts (`/health` green) and `/config` reports
      `cloud_available: false` rather than crashing.

## 8. Sessions and persistence (AC6)

- [ ] Open two sessions in two browser tabs. Ask different questions in
      each. Confirm context doesn't bleed between them.
- [ ] Restart the `api` container (`docker compose restart api`). Reload
      the UI — prior sessions and messages are still there.
- [ ] Delete a session. Confirm a confirmation prompt appears first
      (destructive, unrecoverable per the DB cascade).

## 9. Responsive and accessibility (design.md §4–5)

- [ ] Resize to <640px width. Session list becomes a drawer; artifact pane
      becomes a tab rather than a side pane.
- [ ] Resize to 640–1023px. Two-column layout with collapsible session
      drawer.
- [ ] Run a quick screen-reader pass (VoiceOver/NVDA/Orca) on a streaming
      answer — confirm it announces incrementally without spamming every
      token.
- [ ] Tab through the whole page once — focus order should be composer →
      send → new message → citation chips, matching visual order.
- [ ] Check contrast on the abstention card and provider badge specifically
      (non-default background colors) with a contrast checker — 4.5:1
      minimum for body text.

## 10. Observability spot check

- [ ] Send a handful of turns, then grep `api` and `agent` logs for one
      `trace_id` — confirm it appears in both services' logs for the same
      turn, with per-stage latency fields present.
- [ ] `GET /health/deps` while everything is healthy — confirm `ok` for
      all three deps. Stop `db` — confirm it flips to `down` independently
      without the whole endpoint erroring.
