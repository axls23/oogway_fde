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
  server.ts             HTTP server, one endpoint: POST /turn (streaming), GET /healthz
  session.ts             createAgentSession wiring per architecture.md §8.2;
                          writes agentDir/models.json from models.ollama.json template
  events.ts               maps Pi's session events to the SSE stage/token/citation frames
  tools/
    search-transcripts.ts  defineTool wrapping POST api:8000/internal/retrieve
    create-artifact.ts      defineTool posting to api, returns confirmation only
.pi/skills/ship30-essay/SKILL.md
.pi/skills/artifact-html/SKILL.md
models.ollama.json        template for the custom Ollama provider entry (pi-sdk.md)
package.json               exact pins, @earendil-works/pi-coding-agent@0.84.3
```

## Non-negotiable behaviors

- `createAgentSession` is called with `noTools: "builtin"` and
  `customTools: [searchTranscripts, createArtifact]` only.
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
