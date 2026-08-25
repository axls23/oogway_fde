# web/ — React + Vite frontend

Built against `../contracts/openapi.yaml` (generate or hand-write a typed
client matching it exactly) and `../contracts/sse-frames.schema.json` (the
frame parser must switch on the same `event:` names). See `../design.md`
for UI/UX principles, states, and accessibility requirements — this file
covers only structural and behavioral constraints.

Root invariants in `../CLAUDE.md` apply, particularly: the artifact iframe
must use `sandbox="allow-scripts"` and must never add `allow-same-origin`.

## Structure

```
src/
  api/            typed client generated from/matching contracts/openapi.yaml
  sse/             SSE frame parser + typed event union matching sse-frames.schema.json
  components/
    Chat/           message list, composer, streaming token renderer
    Sessions/        session list/create/delete
    Citations/       citation chips, expand-to-snippet (F2) — no second model call
    ArtifactViewer/   sandboxed iframe (HTML) + sanitized markdown renderer, preview/source toggle
    ProviderBadge/    reads GET /config, renders active provider + model
    Capabilities/       ActiveCapabilities — reads config.capabilities (same
                         GET /config payload), shows active skills/tools/
                         plugins per root CLAUDE.md invariant #4
    CapabilitiesSettings/  full-page settings view (App.tsx `view` state,
                         no router): per-session skill toggles (PATCH
                         /sessions/{id}/capabilities, live) and an extension
                         proposal review queue (POST/PATCH /extension-
                         proposals) — proposing/"approving" here never
                         deploys anything, see the component's docstring
    StarterPrompts/    F6 cold-start prompts
  state/           session state, SSE connection lifecycle
```

## Non-negotiable behaviors

- The frontend never calls the `agent` service directly — only `api`.
- Every request/response state has an explicit UI state: loading,
  streaming, error (named provider + retryable banner per ADR-005), empty
  (no sessions yet), abstained (F5 — show the templated gap message, not
  a generic error).
- A silent multi-second wait is a bug. The `stage` SSE frames exist so the
  UI can show "retrieving → outlining → drafting section 3 of 6" during
  Ship 30 generation (F3) — render them, don't swallow them.
- Citation chips expand client-side from data already returned with the
  message (or via `GET /chunks/{id}`) — never trigger a new chat turn to
  show a source.
- The `ArtifactViewer` HTML pane is `<iframe sandbox="allow-scripts" srcdoc={...}>`.
  No `allow-same-origin`, ever, under any refactor.

## Commands

```
npm install --save-exact
npx tsc --noEmit
npm run dev     # :5173
npm run build
```
