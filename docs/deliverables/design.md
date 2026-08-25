# design.md — The Lenny Growth Assistant

Companion to `PRD.md` (flows, personas, acceptance criteria) and
`architecture.md` (component boundaries, SSE protocol). This document
covers UI/UX principles, information architecture, interaction states,
responsive behavior, and accessibility — the decisions a reviewer can't
infer from the API contract alone.

**How to read this document.** The client's engagement brief is explicit:
the product/growth team wants grounded answers, reusable content and
rendered artifacts *"without needing to understand prompts, models, or
infrastructure."* That constraint runs the other way for this document —
every interface decision below is traced back to the specific backend
guarantee that makes it true, not just described as a visual choice. §1 is
that trace, made explicit, before anything else. A clickable reference
build of every screen referenced below lives in
`design-canvas/lenny-frontend-cascade/` (open `lenny-growth-assistant.html`
in a browser) — it is pixel-matched to `web/src`'s real component styles,
not a separate mockup.

---

## 1. From backend guarantee to interface

Each row is a promise made in code (root `CLAUDE.md`, `architecture.md`'s
ADRs, `retrieval.py`) and the one UI element that has to exist for a
non-technical user to actually receive that promise. If the row on the
right didn't exist, the guarantee on the left would be true in the
codebase and invisible to the person it's for.

| Backend guarantee | Where it's enforced | What the client sees | Why it has to be visible |
|---|---|---|---|
| Citations are built from the ranked chunk list `/internal/retrieve` returns — never parsed from model text (root `CLAUDE.md` invariant 1) | `services/retrieval.py`, `services/turn.py` | Citation chips beneath the answer, carrying guest + episode, expanding to the **verbatim** retrieved snippet | P1's whole reason for asking is citability — an answer she can't spot-check in under a minute isn't worth more than a Slack guess (PRD §1) |
| The relevance floor is a Python `if` guard checked *before* any model call, not a prompt instruction (root `CLAUDE.md` invariant 2) | `retrieval.py` | A visually distinct **"Outside the corpus"** card — calm, neutral, never styled as an error | A refusal the model talked itself into and a refusal the system enforces look identical unless the UI insists otherwise. This is what makes the abstention rate metric (PRD §3) trustworthy to a client reading the screen, not just the eval report |
| No silent failover between providers — an unreachable provider is a structured `503`, never a quiet switch to the other one (ADR-005) | `services/agent_client.py`, `provider.py` | A persistent provider badge in the header (`ollama · qwen2.5:7b-instruct`), and on failure a **named** red banner with Retry | If the badge weren't chrome, ADR-005 would be a backend promise nobody could verify from the product |
| The `stage` SSE frames exist because a synchronous multi-call pipeline (condense → retrieve → outline → per-section → assemble) is real, not instant (PRD F3) | `services/turn.py`, `services/ship30.py` | A single-line status chip that **replaces itself in place** — "Searching Lenny's transcripts…" → "Drafting section 3 of 5…" | A silent 60–180s wait reads as broken regardless of what's actually happening server-side; the honest fix is showing the pipeline, not hiding it |
| Generated HTML/Markdown is sanitized server-side and rendered in an iframe with `sandbox="allow-scripts"` and no `allow-same-origin` (ADR-004) | `services/sanitize.py`, `ArtifactViewer` | An artifact pane with a visible amber border and a header reading *"Generated content — sandboxed, scripts run in an isolated context, no network access"* | A user who can't tell rendered model output from the application's own UI can't reason about what to trust — the boundary has to be a visible fact, not implementation detail |
| Each session's context is isolated in Postgres; the agent itself is stateless per turn (ADR-002) | `db/models.py`, `agent/src/session.ts` | Independent session list, one click from anywhere, with a destructive-confirm on delete | Both personas run parallel investigations (a pricing question *and* a memo draft) — losing that isolation in the UI would silently break a backend guarantee that already holds |

The five screens in `design-canvas/lenny-frontend-cascade/` are the direct
output of this table, not a separate design pass: `Main.dc.html` is rows
1 and 6, `ShipThirty.dc.html` is rows 4 and 5, `States.dc.html` is rows 2
and 3, `ColdStart.dc.html` is the cold-start instance of row 6,
`Mobile.dc.html` is every row re-tested under the responsive constraint in
§5.

---

## 2. Principles

**1. Show the pipeline, don't hide it.** PRD §6 F3 states a silent
two-minute spinner "reads as broken." Every stage the backend emits
(`retrieving`, `outlining`, `drafting section N of M`, `assembling`) is
rendered as a visible, labeled step. The system is honest about being a
multi-stage pipeline rather than performing instant intelligence.

**2. A citation is a claim you can check in one click, not a claim you take
on faith.** Every citation chip expands inline to the verbatim retrieved
snippet with zero additional latency and zero additional model call (F2).
This is the single UI element the target persona (PRD §1, "citability" is
the whole point) will use most.

**3. Refusal is a first-class state, not an error.** When the corpus
doesn't support a question (F5), the UI renders a distinct, calm state —
not a red error banner — naming the gap and offering adjacent topics. An
abstention is the system working correctly, and the visual language must
not punish the user for asking a fair question the corpus can't answer.

**4. The provider is never invisible.** ADR-005's no-silent-failover
guarantee is only meaningful if a human can see it. The provider badge is
persistent chrome, not a settings-page fact.

**5. Untrusted content looks different from trusted chrome.** The artifact
pane has a visible boundary (border, header bar reading "Generated content
— sandboxed") so a user never mistakes rendered HTML for part of the
application's own UI.

**6. The client never has to read a log to trust the product.** Every one
of the five backend guarantees in §1 has to be verifiable by looking at
the screen, because the engagement brief rules out asking this client to
open a terminal, a trace, or a prompt to confirm the system behaved.

---

## 3. Information architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Header:  App name · Provider badge (● ollama · qwen2.5:7b)      │
├───────────────┬─────────────────────────────┬───────────────────┤
│ Session list   │ Chat column                  │ Artifact pane     │
│ (collapsible)  │  - message list               │ (opens on demand, │
│  - New chat    │  - streaming assistant turn   │  closes to give   │
│  - past titles │  - citation chips inline      │  chat full width) │
│                │  - composer                   │  - preview/source │
│                │  - starter prompts (F6, only  │    toggle         │
│                │    shown on an empty session) │  - copy / download│
└───────────────┴─────────────────────────────┴───────────────────┘
```

Three columns collapse to two (session list becomes a drawer) below
1024px, and to one (chat only, artifact pane becomes a full-screen
overlay reachable by a tab) below 640px — see §5. `Main.dc.html` and
`ColdStart.dc.html` in the reference build are this layout at rest and
empty; `Mobile.dc.html` is the collapsed form.

---

## 4. Interaction states

### Chat / message turn

| State | Presentation | Reference screen |
|---|---|---|
| Empty session | Starter prompts (F6): three cards, each naming a capability ("Ask a grounded question", "Draft a Ship 30 essay", "Generate a one-pager") | `ColdStart.dc.html` |
| Sending | Composer disables, user message appears immediately (optimistic) | `Main.dc.html` |
| `stage: retrieving` | A single-line status chip above the response area: "Searching Lenny's transcripts…" | `ShipThirty.dc.html` |
| `stage: drafting` (F3, staged) | Status chip updates: "Drafting section 3 of 6…" — replaces the previous stage text in place, does not stack | `ShipThirty.dc.html` |
| `token` streaming | Assistant text grows in place, markdown rendered incrementally | `Main.dc.html` |
| `citation` frames | Chips render beneath the message as they arrive, before the message finishes streaming — the user sees sources accumulate, not appear all at once at the end | `Main.dc.html` |
| Abstained (F5) | Distinct card style (neutral, not red): "Outside the corpus — closest topics indexed: …" | `States.dc.html` |
| Provider error (ADR-005) | Red banner at the top of the chat column, names the provider, states "not falling back to cloud automatically," offers Retry | `States.dc.html` |
| Model timeout, partial answer | Streamed text stays visible, appended with a distinct "Response was cut off" notice — the partial answer is not discarded | `States.dc.html` |

### Citation chip

Default: `[rank] Guest Name · Episode Title`. Click → expands inline
(accordion, not a modal — keeps chat scroll position) to show the
verbatim chunk text plus a link to the YouTube episode. Second click
collapses it. No loading spinner on expand — data already arrived with
the message. Below 640px it opens as a bottom sheet instead (§5).

### Artifact pane

| State | Presentation |
|---|---|
| Generating (F3/F4) | Pane opens immediately showing the same staged-progress chip as the chat, so the user isn't staring at a blank pane |
| Ready | Preview tab active by default; Source tab shows raw Markdown/HTML in a read-only code view |
| HTML artifact | Sandboxed iframe, bordered, labeled "Generated content — sandboxed, scripts run in an isolated context, no network access" |
| Copy / Download | Copy copies the raw source (not the rendered preview); Download saves the `.md` or `.html` file |

### Session list

New chat is always one click from anywhere. Deleting a session asks for
confirmation (destructive, and per `architecture.md`'s cascade,
unrecoverable — messages, citations and artifacts are deleted with it).

---

## 5. Responsive behavior

| Breakpoint | Layout | Reference screen |
|---|---|---|
| ≥ 1024px | Three columns as drawn in §3 | `Main.dc.html`, `ShipThirty.dc.html` |
| 640–1023px | Session list collapses to a drawer (hamburger toggle); chat and artifact pane share the remaining width, artifact pane can be closed to give chat full width | — |
| < 640px | Single column. Artifact pane becomes a full-screen view reached via a tab at the top of the chat ("Chat" / "Artifact"); citation chip expansion becomes a bottom sheet rather than inline accordion, to avoid pushing chat content far down on a small screen | `Mobile.dc.html` |

The chat composer is sticky-positioned at the viewport bottom on all
breakpoints, with safe-area padding for mobile browser chrome.

---

## 6. Accessibility

- All streaming text updates use `aria-live="polite"` on the assistant
  message container so screen readers announce new content without
  interrupting.
- Stage-progress chips are announced via the same live region, replacing
  rather than appending, so a screen reader user gets "Drafting section 3
  of 6" once, not a growing list of every stage transition.
- Citation chips are real `<button>` elements (not `<div onClick>`),
  keyboard-reachable, `aria-expanded` reflects accordion state.
- The artifact iframe has a `title` attribute describing its content, and
  the pane's sandboxing notice is real text, not a tooltip-only affordance.
- Color is never the only signal: the abstention state and the error state
  are visually distinct by icon and copy, not by hue alone, for a color-
  blind user — see `States.dc.html`, where both live in the same session
  list so they can be compared directly.
- Focus order: composer → send → (new) message → citation chips, in DOM
  order, so keyboard-only navigation matches visual reading order.
- Minimum contrast 4.5:1 for body text against both light and dark
  backgrounds; the provider badge and abstention card are tested
  explicitly since they use non-default background colors.

---

## 7. Design decisions worth stating explicitly

- **No dark-mode toggle in v1.** Respect `prefers-color-scheme` only. A
  manual toggle is a real feature with its own state and testing surface;
  the one-day budget (PRD §5) spends it elsewhere.
- **No message editing or regeneration in v1.** Consistent with PRD's
  excluded scope (no conversation branching, ADR-002) — the UI doesn't
  offer an affordance for a capability the backend doesn't have.
- **Starter prompts are static, not personalized.** They exist to make the
  first 90 seconds designed rather than blank (PRD F6); personalizing them
  would need usage data this system doesn't collect in v1.
- **The failure states live in the session list, not a settings page.**
  `States.dc.html` shows abstention, a provider error, and a timeout as
  three ordinary past sessions a user clicks into — because that's how a
  real user actually encounters them: by resuming a session, not by being
  walked through a demo of what could go wrong.
- **The reference build is the spec.** Every table above names the exact
  `.dc.html` screen it describes; if this document and the reference build
  ever disagree, the reference build — because it's pixel-matched to
  `web/src`'s actual `theme.css` and component styles — is the one to fix
  this document against, not the reverse.
