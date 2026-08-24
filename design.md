# design.md — The Lenny Growth Assistant

Companion to `PRD.md` (flows, personas, acceptance criteria) and
`architecture.md` (component boundaries, SSE protocol). This document
covers UI/UX principles, information architecture, interaction states,
responsive behavior, and accessibility — the decisions a reviewer can't
infer from the API contract alone.

---

## 1. Principles

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

---

## 2. Information architecture

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
overlay reachable by a tab) below 640px — see §5.

---

## 3. Interaction states

### Chat / message turn

| State | Presentation |
|---|---|
| Empty session | Starter prompts (F6): three cards, each naming a capability ("Ask a grounded question", "Draft a Ship 30 essay", "Generate a one-pager") |
| Sending | Composer disables, user message appears immediately (optimistic) |
| `stage: retrieving` | A single-line status chip above the response area: "Searching Lenny's transcripts…" |
| `stage: drafting` (F3, staged) | Status chip updates: "Drafting section 3 of 6…" — replaces the previous stage text in place, does not stack |
| `token` streaming | Assistant text grows in place, markdown rendered incrementally |
| `citation` frames | Chips render beneath the message as they arrive, before the message finishes streaming — the user sees sources accumulate, not appear all at once at the end |
| Abstained (F5) | Distinct card style (neutral, not red): "Lenny's Podcast doesn't cover this directly. Closest topics indexed: …" |
| Provider error (ADR-005) | Red banner at the top of the chat column, names the provider, states "not falling back to cloud automatically," offers Retry |
| Model timeout, partial answer | Streamed text stays visible, appended with a distinct "Response was cut off" notice — the partial answer is not discarded |

### Citation chip

Default: `[Guest Name · Episode Title]`. Click → expands inline (accordion,
not a modal — keeps chat scroll position) to show the verbatim chunk text
plus a link to the YouTube episode. Second click collapses it. No loading
spinner on expand — data already arrived with the message.

### Artifact pane

| State | Presentation |
|---|---|
| Generating (F3/F4) | Pane opens immediately showing the same staged-progress chip as the chat, so the user isn't staring at a blank pane |
| Ready | Preview tab active by default; Source tab shows raw Markdown/HTML in a read-only code view |
| HTML artifact | Sandboxed iframe, bordered, labeled "Generated content — sandboxed, scripts run in an isolated context, no network access" |
| Copy / Download | Copy copies the raw source (not the rendered preview); Download saves the `.md` or `.html` file |

### Session list

New chat is always one click from anywhere. Deleting a session asks for
confirmation (destructive, and per architecture.md's cascade, unrecoverable
— messages, citations and artifacts are deleted with it).

---

## 4. Accessibility

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
  blind user.
- Focus order: composer → send → (new) message → citation chips, in DOM
  order, so keyboard-only navigation matches visual reading order.
- Minimum contrast 4.5:1 for body text against both light and dark
  backgrounds; the provider badge and abstention card are tested
  explicitly since they use non-default background colors.

---

## 5. Responsive behavior

| Breakpoint | Layout |
|---|---|
| ≥ 1024px | Three columns as drawn in §2 |
| 640–1023px | Session list collapses to a drawer (hamburger toggle); chat and artifact pane share the remaining width, artifact pane can be closed to give chat full width |
| < 640px | Single column. Artifact pane becomes a full-screen view reached via a tab at the top of the chat ("Chat" / "Artifact"); citation chip expansion becomes a bottom sheet rather than inline accordion, to avoid pushing chat content far down on a small screen |

The chat composer is sticky-positioned at the viewport bottom on all
breakpoints, with safe-area padding for mobile browser chrome.

---

## 6. Design decisions worth stating explicitly

- **No dark-mode toggle in v1.** Respect `prefers-color-scheme` only. A
  manual toggle is a real feature with its own state and testing surface;
  the one-day budget (PRD §5) spends it elsewhere.
- **No message editing or regeneration in v1.** Consistent with PRD's
  excluded scope (no conversation branching, ADR-002) — the UI doesn't
  offer an affordance for a capability the backend doesn't have.
- **Starter prompts are static, not personalized.** They exist to make the
  first 90 seconds designed rather than blank (PRD F6); personalizing them
  would need usage data this system doesn't collect in v1.
