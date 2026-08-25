# agent/ — Pi sidecar

**Before writing any code against the Pi SDK, read `../docs/vendor/pi-sdk.md`
in full. It is the only authority on that API** — the SDK post-dates this
coding agent's training data (architecture.md ADR-007). Do not recall
`createAgentSession`, `defineTool`, or any other symbol from general
training; every symbol used here must appear in that vendored file.

Root invariants in `../CLAUDE.md` apply. In particular: `noTools: "builtin"`
is not optional, and this service never reads Postgres directly for
application state — history arrives on each request from `api` and is
rehydrated into `session.agent.state.messages` per turn (ADR-002).

## Structure

```
src/
  server.ts             HTTP server: POST /turn (streaming), GET /healthz, GET /capabilities
  session.ts             createAgentSession wiring per architecture.md §8.2;
                          writes agentDir/models.json from models.ollama.json template
  events.ts               maps Pi's session events to the SSE stage/token/citation frames
  capabilities.ts         extension manifest allowlist (verifyExtensions) + the
                          skills/extensions/tools snapshot served by GET /capabilities
  tools/
    search-transcripts.ts  defineTool wrapping POST api:8000/internal/retrieve
    create-artifact.ts      defineTool posting to api, returns confirmation only
    edit-artifact.ts         defineTool PATCHing an existing artifact, returns confirmation only
.pi/skills/ship30-essay/SKILL.md
.pi/skills/artifact-html/SKILL.md
.pi/extensions/manifest.json  allowlist: path + sha256 + declared tool names per
                               extension. Empty by default — see invariant #4 below.
models.ollama.json        template for the custom Ollama provider entry (pi-sdk.md)
package.json               exact pins, @earendil-works/pi-coding-agent@0.84.3
```

## Non-negotiable behaviors

- `createAgentSession` is called with `noTools: "builtin"` and
  `customTools: [searchTranscripts, createArtifact, editArtifact]` only.
  `edit_artifact` revises an artifact `create_artifact` already made
  (PATCH, not a new tool class) — it does not create a fourth capability
  bucket, and it still cannot touch anything outside the `artifacts` table
  row it's given an id for (api enforces the id belongs to the calling
  session; see routers/internal.py).
- `DefaultResourceLoader` is constructed with `noExtensions: !AGENT_EXTENSIONS_ENABLED`
  (default false) — Pi extensions are arbitrary in-process code that can
  register any tool with no sandbox, so they're off unless explicitly
  turned on. When on, `verifyExtensions()` in `capabilities.ts` must pass
  before a session is ever prompted: every loaded extension needs a
  `agent/.pi/extensions/manifest.json` entry matching its exact path,
  content sha256, and the tool names it's approved to register. Any
  unlisted extension, hash drift, or undeclared tool registration throws
  and aborts session construction — never load a partial/best-effort set.
  Do not relax this by catching `ExtensionManifestViolation` and
  continuing.
- `search_transcripts`'s tool result text is explicitly delimited and
  labelled as untrusted retrieved data (e.g. wrapped in a clear
  `<retrieved_transcript_excerpts>` marker) — this corpus is untrusted
  input and a prompt-injection surface (§8.5).
- Provider/model come from `LLM_PROVIDER` / `LLM_MODEL` env vars, resolved
  at session-construction time — no hardcoded default provider in code
  beyond what `.env.example` documents.
- `PI_OFFLINE=1` must be respected — `ModelRuntime.create()` is called in
  a way that does not attempt a network refresh of the model catalog.
- Every Pi session event maps to exactly one SSE frame type per the table
  in architecture.md §8.4 — don't invent additional frame types outside
  `contracts/sse-frames.schema.json`.
- If Ollama is unreachable when a turn starts, fail with a structured
  error the caller (`api`) can turn into the 503 — don't retry into a
  cloud provider.

## Commands

```
npm install --save-exact
npx tsc --noEmit
npx biome check .
npm run dev    # ts-node/tsx on :8100
```
