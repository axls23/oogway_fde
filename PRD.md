# PRD — The Lenny Growth Assistant

| | |
|---|---|
| **Status** | Draft for client review |
| **Version** | 1.0 |
| **Engagement** | Forward-deployment, single-engineer, one-day build window |
| **Stack** | React/Vite · FastAPI · Pi Coding Agent (Node sidecar) · Ollama · Postgres + pgvector |
| **Corpus** | `ChatPRD/lennys-podcast-transcripts` — 303 episode transcripts with YAML frontmatter |

---

## 0. Discovery brief

A product and growth team asked for an internal assistant over Lenny's Podcast transcripts. The brief was deliberately incomplete: no named user, no volume estimate, no definition of "grounded," no infrastructure. This document records the requirements I inferred, the assumptions I made to close the gaps, what I chose not to build, and the evidence that would tell us any of it was wrong.

The engagement has an unusual property worth stating early: **there are two consumers of this system.** The product team uses the running application. A client engineer must be able to clone, run, understand and extend it. Design decisions that serve only the first are incomplete deliveries, so operability is treated as a product requirement throughout, not an afterthought.

---

## 1. User

### Primary — P1, "Senior PM mid-decision"

Owns a live decision: a pricing change, an activation drop, a PRD due Thursday. Needs a defensible position she can put in a document with a name attached to it. *"Brian Chesky said X"* carries internal weight that *"research suggests X"* does not.

- **Job to be done:** "When I'm about to make a product call, help me find what operators who've done this already said, so I can decide faster and defend the decision."
- **Success looks like:** an answer with two or three named sources she can spot-check in under a minute.
- **Today's alternative:** scrubbing YouTube, half-remembered episodes, Slack-asking a colleague. Twenty to forty minutes, poor recall, no citation trail.

### Primary — P2, "Growth lead producing"

Needs an artifact out the door: a leadership memo, an internal essay, a one-pager for a channel experiment. Treats the assistant as a drafting engine over a corpus he already trusts.

- **Job to be done:** "When I need to write something persuasive about growth, give me a structured draft grounded in real operator experience so I'm editing rather than starting cold."
- **Success looks like:** a formatted artifact he can copy into Notion or Google Docs with light editing.
- **Today's alternative:** a blank page, or a general LLM that invents plausible-sounding examples he then has to strip out.

### Secondary — the operating engineer

Runs the system, diagnoses failures, extends it with a new skill or a refreshed corpus. Never types into the chat. Consumes the README, `architecture.md`, structured logs and health endpoints.

### Explicit non-users

Executives wanting dashboards, external customers, anyone needing multi-tenant access control. Serving them would force auth, quotas and RBAC into a one-day build and degrade the two personas above.

### The behavioural trait that drives the architecture

Both personas **arrive with a situation, not a query.** They type *"our activation dropped after we added a second onboarding step, what do people say about this."* That is a poor embedding query and an excellent conversational opener. Follow-ups are pronominal — *"what about B2B?"*, *"the second one"*, *"expand on that."* Section 7.3 exists because of this observation.

---

## 2. Problem

Lenny's Podcast is one of the densest sources of tactical product and growth advice available, and it is effectively unsearchable. 303 episodes of long-form conversation means the knowledge exists but cannot be retrieved at the moment of decision. Teams fall back on whoever happens to remember the right episode.

Two failure modes bound the solution:

1. **Search-shaped tools** (grep, YouTube search, transcript keyword search) return locations, not answers. The user still does the reading and the synthesis.
2. **General-purpose LLMs** return answers, not sources. They will confidently attribute a framework to a guest who never said it. For a user whose entire reason for asking is *citability*, an unsourced answer is worse than no answer — it carries the cost of verification without the benefit of trust.

**The assistant's job is to sit exactly between these:** synthesis with an auditable trail back to a named guest and episode, and a visible refusal when the corpus genuinely doesn't cover the question.

**Pain removed:** twenty to forty minutes of manual retrieval per decision, and the credibility risk of quoting something the podcast never said.

---

## 3. Success metrics

### Primary product metric

**Grounded answer rate — target ≥ 85%.** On a fixed 20-question evaluation set drawn from known corpus topics, the percentage of answers where at least one cited chunk substantively supports the claim, judged by a human rubric. Chosen because it measures the one thing the product exists to do; latency and polish are worthless if this number is low.

### Guardrail metric

**Correct abstention rate — target 5/5.** On five deliberately out-of-corpus questions (semiconductor supply chains, tax law, personal advice), the system must refuse and name the gap rather than fabricate. This is a *counter-metric*: a system can inflate grounded answer rate by answering everything confidently, and this catches that.

### Secondary product metric

**Artifact acceptance — target ≥ 70%.** Percentage of generated Ship 30 essays and artifacts that pass structural validation on first generation (word count within ±100 of 1,250, ≥ 4 headings, ≥ 3 distinct cited sources, no empty sections).

### Operational metrics

| Metric | Target | Why |
|---|---|---|
| p95 time-to-first-token, local model | < 3 s | Below the threshold where a user assumes the system is broken |
| Ship 30 essay end-to-end, local model | < 180 s with staged progress | Long is acceptable; *silent* is not |
| Cold start: fresh clone → first grounded answer | < 10 min, zero API keys | Directly measures handoff quality |
| Unhandled 5xx rate | < 1% of turns | Resilience requirements are met or they aren't |

### How they're measured

Every turn writes a structured log line carrying `trace_id`, `session_id`, rewritten query, retrieved chunk IDs with scores, provider, model, and stage latencies. The evaluation set lives in `tests/eval/` and runs as a script, so any change to chunking or prompting is scored rather than eyeballed.

---

## 4. Assumptions

Recorded because the brief was incomplete. Each carries the signal that would invalidate it.

| # | Assumption | Rationale | Risk if wrong | Invalidation signal |
|---|---|---|---|---|
| A1 | Primary user is an IC PM / growth lead, not an executive | The corpus is tactical; exec users would want summary dashboards | Wrong output shape and tone throughout | Users ask for trends and aggregates rather than specific advice |
| A2 | Retrieval beats long-context | 303 long-form transcripts exceed any locally-runnable context window by orders of magnitude | Wasted index infrastructure | A local model with a very large usable window becomes viable |
| A3 | The vector index is **pre-built and seeded**, not built at first run | Evaluator patience is the scarcest resource in the engagement | A 20-minute cold start destroys the first impression | Ingest of the full corpus measured under 5 minutes |
| A4 | The citation unit is the episode, keyed on frontmatter (`guest`, `title`, `youtube_url`, `publish_date`) | The metadata is structured and already present in every transcript | Citations become unverifiable | Users ask "where in the episode?" more than "which episode?" |
| A5 | Single-user, no authentication; `user_metadata` is a populated but unenforced column | Not requested, and auth is pure cost against a one-day budget | Cannot deploy beyond a single trusted team | Any request to share sessions between people |
| A6 | Local model is the **default**; cloud is opt-in and degrades gracefully when absent | The demo must run with an empty `.env` | Startup crash for any evaluator without an API key | — |
| A7 | Ship 30 principles are extracted once and committed as a versioned skill artifact | The brief explicitly asks for encoding rather than prompting | Reads as an unstructured one-off prompt; fails §4.2 | — |
| A8 | ~~Transcripts carry no reliable per-line timestamps~~ **Invalidated during build.** Every speaker turn is timestamped (`Guest Name (HH:MM:SS):`), consistently across a spot-check of the corpus. `chunks.start_seconds` (nearest preceding speaker-turn timestamp) was added to the schema before any code depended on it, and citations deep-link to `youtube_url&t={start_seconds}s`. | Original assumption was a guess pending verification | (resolved) | Corpus clone + spot-check, 2026-08-24 |
| A9 | Query volume is low — single team, tens of turns per day | Internal tool for one team | Over-engineering for scale we don't have | — |

---

## 5. Scope

### In scope

- Multi-turn grounded chat with independent session context and full persistence
- Conversational query rewriting before retrieval
- Vector retrieval over transcript chunks with per-answer citations and inspectable snippets
- Explicit abstention path when retrieval is weak
- Ship 30 for 30 essay skill with deterministic assembly and structural validation
- Markdown and HTML/CSS artifact generation with a sandboxed in-app viewer
- Provider toggle (Ollama default, Anthropic opt-in) with no code changes
- Docker Compose one-command startup, `.env.example`, structured logs, health endpoints
- Automated tests for API contracts, retrieval, routing and persistence; manual UI test plan

### Explicitly out of scope

| Excluded | Why |
|---|---|
| Authentication, multi-tenancy, RBAC | Not requested; unbounded cost against a one-day budget (A5) |
| Cross-encoder re-ranking | Adds a second model to the local footprint for a marginal gain the eval set can't yet justify |
| Hybrid BM25 + vector retrieval | Real gain, but pgvector alone must be proven insufficient first |
| Artifact editing and version history | Users export to Notion or Docs and edit there; duplicating an editor is waste |
| Automated corpus refresh / scheduled re-ingest | The *procedure* is documented and scripted; the scheduler is not built |
| Voice, mobile-native app, export integrations | Well outside the brief |

### Conditional scope cut

If measured ingest of all 303 episodes exceeds 25 minutes on the build machine, the seeded index ships with a **curated subset selected via the repository's own `index/` topic files** (product management, growth strategy, product-market fit, leadership), and the full-corpus ingest remains available as a documented command. This is a deliberate trade of coverage for a working cold start, not a silent shortfall — the README states which episodes are indexed and how to index the rest.

---

## 6. Flows

Six flows, weighted by expected share of turns. The weights are the optimization budget.

### F1 — Grounded Q&A with follow-ups · ~55% of turns

1. User sends a situational message.
2. Backend condenses the last N turns plus the new message into a standalone query; both raw and rewritten forms are logged.
3. Rewritten query is embedded and searched against `chunks`; episodes cited earlier in the session receive a soft score boost.
4. Top results above the relevance floor are passed to the agent as tool output.
5. Answer streams token-by-token; citation chips render beneath it with guest name and episode title.
6. Turn, citations and latency are persisted.

**Edge cases:** first turn has no history to condense; a follow-up that changes topic entirely must not be over-boosted toward prior episodes.

### F2 — Provenance check · ~15% of turns, rarely standalone

User clicks a citation chip → the frontend expands the **verbatim retrieved snippet** plus a link to the episode. No second model call. A citation the user cannot inspect is a claim, not a source.

### F3 — Ship 30 essay · ~10% of turns, 100% of the §4.2 rubric

1. User asks for an essay on the current thread's topic.
2. Retrieval gathers a wider result set than F1.
3. Model produces a **structured JSON outline** — hook, 4–6 sections, takeaway.
4. Each section is generated in a separate call scoped to its own supporting chunks.
5. Python assembles the document deterministically; formatting is guaranteed by code, not by the model.
6. Validator checks word count, heading count, bold density, citation coverage; failures trigger a bounded repair pass on the offending section only.
7. Result opens in the artifact viewer.

The UI shows staged progress — *retrieving → outlining → drafting section 3 of 6 → assembling*. A silent two-minute spinner reads as broken; a staged one is both better UX and an honest depiction of the pipeline.

### F4 — Artifact generation · ~10% of turns

User asks for a document or HTML snippet → agent calls `create_artifact` → content is sanitized → the pane splits and renders it → user toggles preview/source and copies or downloads.

### F5 — Corpus miss · ~5% of turns, disproportionate trust weight

Retrieval returns nothing above the relevance floor → the request **short-circuits before the model sees weak context** → a templated response names the gap and offers the nearest adjacent topics from the index. Evaluators probe this deliberately; small models fail it worst.

### F6 — Cold start · runs once, weighted heavily

`docker compose up` → migrations → seeded index loads → health endpoints green → UI opens with the provider badge reading `ollama:qwen2.5:7b` and three starter prompts, each exercising a different capability. The first ninety seconds are a designed experience, not a side effect.

---

## 7. Design choices

### 7.1 Component boundaries

```
React/Vite ──► FastAPI (Python)              ──► Postgres + pgvector
   │             sessions, messages, artifacts,      episodes, chunks,
   │             /retrieve, /health, /config          embeddings, sessions,
   │                    │  HTTP + SSE                 messages, citations
   │                    ▼
   └───────────► Pi sidecar (Node/TypeScript)
                   tools:  search_transcripts → FastAPI /retrieve
                           create_artifact
                   skills: ship30-essay, artifact-html
                   provider: ollama | anthropic
```

**The load-bearing trade-off:** the brief mandates FastAPI, and Pi is a TypeScript library. That forces a language boundary. Three options were considered — subprocessing the `pi` CLI per turn (lowest effort, fragile streaming, poor logs), reimplementing the agent loop in Python (fails a hard requirement), and a thin Node sidecar exposing one streaming endpoint. The sidecar wins: roughly 150 lines, a clean and explainable service boundary, real token streaming, and Pi's own session JSONL as a free audit trail. The cost is a third container and one extra network hop, which is acceptable at this scale (A9).

### 7.2 Data model

```sql
episodes    (id, guest, title, youtube_url, video_id, publish_date,
             duration_seconds, source_path, content_hash)
chunks      (id, episode_id → episodes, ordinal, text, token_count,
             embedding vector(768))
sessions    (id, title, provider, model, user_ref, created_at, updated_at)
messages    (id, session_id → sessions, role, content, trace_id,
             provider, model, latency_ms, token_in, token_out, created_at)
citations   (id, message_id → messages, chunk_id → chunks, rank, score)
artifacts   (id, session_id, message_id, kind, content, sanitized, created_at)
ingest_runs (id, started_at, finished_at, episode_count, chunk_count,
             embed_model, status)
```

`chunks.text` is stored alongside the embedding specifically to serve F2 without a second model call. `citations` as a first-class table rather than a JSON blob on `messages` makes "which episodes does this system actually cite?" a one-line query — useful for both evaluation and debugging. `content_hash` on episodes makes re-ingest idempotent. `ivfflat` index on `embedding`, btree on `messages.session_id`.

### 7.3 Retrieval

Fixed-size chunking at ~800 tokens with 15% overlap, split on speaker turns where the transcript structure allows. Podcast speech is discursive and lacks section headers, so semantic chunking offers little over fixed-size at meaningfully higher cost.

The pipeline is: **condense → embed → top-k=8 → session boost → relevance floor → return 4.** The condensation step is the single highest-value component in the system. F1 is 55% of turns and its follow-ups are pronominal; embedding *"what about B2B?"* directly returns noise. Condensation runs as a tight low-temperature call returning one line, and both query forms are logged so retrieval failures are diagnosable.

The relevance floor is a Python guard, not a prompt instruction (F5). A 7B model handed weak context will confabulate regardless of what the system prompt asks. The threshold is tuned against the five out-of-corpus evaluation questions.

### 7.4 Agent layer and routing

The Pi session is restricted to an explicit allowlist — `search_transcripts` and `create_artifact` only. No `bash`, `read`, `write` or `edit`. The tool allowlist *is* the routing boundary and the primary containment control; an agent that cannot touch the filesystem cannot be prompt-injected into touching the filesystem. Skills (`ship30-essay`, `artifact-html`) are versioned files in the repository rather than strings in application code, satisfying the "encode, don't prompt" requirement and making the writing principles reviewable and diffable.

### 7.5 Model configuration

Provider and model come from environment variables consumed by Pi's provider configuration. Switching from local to cloud is an `.env` edit and a container restart — no code change. The active provider is exposed at `GET /config` and rendered as a badge in the UI header.

**Fallback behaviour, documented and implemented:** if the configured provider is unreachable at request time, the backend returns a structured `503` with `retryable: true` and the UI surfaces a banner naming the failed provider. It does **not** silently fail over to the other provider — a user who believes they are talking to a local model must never be silently switched to a cloud one. Silent failover is a data-governance incident, not a resilience feature.

### 7.6 Artifact security

Generated HTML is untrusted by construction. The viewer renders it in an iframe via `srcdoc` with `sandbox="allow-scripts"` and **without** `allow-same-origin`, so scripts run in an opaque origin with no access to app storage, cookies or the parent DOM. A restrictive CSP blocks all network egress (`default-src 'none'; style-src 'unsafe-inline'; img-src data:`), form submission is disabled, and content is size-capped. Markdown travels a separate path through a sanitizer with an allowlisted tag set.

| Permitted | Blocked |
|---|---|
| Inline HTML/CSS layout and styling | Any network request (fetch, XHR, WebSocket, remote fonts, remote images) |
| Inline scripts, sandboxed in an opaque origin | Access to `localStorage`, cookies, parent DOM |
| `data:` images | Form submission, top-level navigation, popups |

The rationale is stated in the README so the operating engineer knows what the viewer permits and why.

### 7.7 Observability and resilience

Every turn carries a `trace_id` through rewriter, retrieval, agent and persistence. Logs are structured JSON with per-stage latency, retrieved chunk IDs and scores, provider and model. `GET /health` is a liveness check; `GET /health/deps` reports Postgres, Ollama and sidecar status independently, so "which layer is broken?" is answerable without reading code.

Five failure modes are handled explicitly, each with a test: missing API key (start anyway, cloud disabled, surfaced in `/config`), Ollama unreachable (structured 503 with banner), model timeout (bounded, streams a partial answer with a truncation notice), empty retrieval (F5 abstention path), database unavailable (fail fast at startup with a clear message rather than serving a broken UI).

All errors share one envelope: `{"error": {"code", "message", "trace_id", "retryable"}}`.

### 7.8 What I would revisit as this grows

Hybrid retrieval and a cross-encoder re-ranker once the eval set shows vector-only recall plateauing. A job queue for essay generation once concurrent users make a 180-second synchronous request untenable. Per-user auth and row-level session scoping the moment a second team touches it. Incremental re-ingest keyed on `content_hash` when the corpus starts updating weekly rather than never.

---

## 8. Acceptance criteria

| # | Criterion | Verification |
|---|---|---|
| AC1 | A fresh clone reaches its first grounded answer in under 10 minutes with an empty `.env` and no API key | Timed rehearsal on a clean directory |
| AC2 | ≥ 85% of the 20-question eval set produces an answer citing at least one substantively relevant episode | `tests/eval/` script + human rubric |
| AC3 | 5/5 out-of-corpus questions produce an explicit refusal naming the gap; zero fabricated attributions | Eval script |
| AC4 | A three-turn pronominal chain (question → "what about B2B?" → "expand on that") retrieves on-topic chunks at every turn | Automated retrieval test asserting rewritten queries |
| AC5 | Every citation chip expands to the verbatim retrieved snippet with no additional model call | Manual UI test + network inspection |
| AC6 | Two concurrent sessions maintain fully independent context; messages persist across a backend restart | Automated persistence test |
| AC7 | A Ship 30 essay generates at 1,250 ± 100 words with ≥ 4 headings and ≥ 3 distinct cited sources, reproducibly on the local model | Automated structural validation over 3 runs |
| AC8 | An HTML artifact containing `<script>fetch('https://example.com')</script>` renders inert with the request blocked | Manual test with browser network panel |
| AC9 | Switching provider requires only an `.env` change and restart; the UI badge updates accordingly | Manual test both directions |
| AC10 | With Ollama stopped, the UI shows a named error banner and the backend returns a structured 503 — and does **not** fail over to cloud | Manual test |
| AC11 | Every turn emits a structured log line with `trace_id`, retrieved chunk IDs and per-stage latency | Log inspection |
| AC12 | `GET /health/deps` reports Postgres, Ollama and sidecar independently | Automated test |

---

## 9. Risks and trade-offs

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Local 7B model fabricates attributions** | High | High | Relevance floor short-circuits before the model sees weak context; citations rendered from retrieval metadata rather than model output, so the model *cannot* invent a source name; abstention is an eval-gated code path |
| **7B tool-calling is unreliable** | Medium | High | Verified as a first-hour spike; `qwen2.5:7b` chosen over `llama3.1:8b` for steadier structured output. Fallback: Python-side intent classification pre-selects the skill and Pi executes with the tool pre-bound |
| **Essay quality collapses on a small model** | High | Medium | Structure is enforced by deterministic Python assembly and validation, not by the model. Sections generated independently against scoped context, then assembled |
| **Ingest too slow for a usable cold start** | Medium | High | Index seeded, not built at runtime (A3); conditional subset cut documented in §5 |
| **Language boundary adds a failure surface** | Medium | Medium | Sidecar exposes one endpoint; independent health reporting; structured 503 on unreachability |
| **Untrusted HTML executes against app origin** | Low | High | Sandboxed opaque-origin iframe, restrictive CSP, no `allow-same-origin`, size cap (§7.6) |
| **Prompt injection via transcript content** | Low | Medium | Tool allowlist excludes all filesystem and shell access; retrieved text is delimited and labelled as data in the tool response |
| **One-day budget forces a visible shortfall** | High | Medium | Build order sequenced so every checkpoint is independently demoable; the last green checkpoint ships, and any cut is documented in this PRD rather than discovered by the evaluator |
| **Data leakage to a cloud provider** | Low | High | Local is the default; no silent failover (§7.5); provider always visible in the UI |

**The headline trade-off:** a local 7B model was mandated for the demo, and small models are unreliable at long-form structure, citation fidelity and refusal. Rather than fight this with prompt engineering, the design moves every guarantee it can into deterministic code — retrieval floors, citation rendering from metadata, essay assembly and validation in Python. The model is used for what it is good at (local synthesis and prose) and constrained everywhere it is not. The cost is a more complex pipeline than a single-prompt approach; the benefit is that quality degrades gracefully rather than catastrophically when the model is weak.

---

## 10. Implementation plan

Timeboxed to a one-day window. Every checkpoint leaves a demoable system; if the schedule slips, the last green checkpoint ships.

| Block | Deliverable | Gate |
|---|---|---|
| **H0–1** | Three spikes: Pi + Ollama tool-calling, embedding throughput extrapolated to 303 episodes, transcript timestamp check. Repo skeleton, Compose with Postgres + pgvector, `.env.example` | `docker compose up` → `/health` green |
| **H1–3** | **Eval set written by hand first** (20 in-corpus + 5 out). Ingestion: frontmatter parse → chunk → embed → store, idempotent on `content_hash` | 25 questions committed; corpus indexed |
| **H3–5** | Query rewriter + `/retrieve` with citation payload and relevance floor. Retrieval-only eval run | AC2 threshold met on retrieval alone; AC4 passes |
| **H5–7** | Pi sidecar, `search_transcripts` tool, SSE through FastAPI, session + message persistence, citation-expand endpoint | AC5, AC6 pass; multi-turn chat cites sources end to end |
| **H7–9** | Frontend: chat, session list, provider badge, streaming, empty/loading/error states, starter prompts | AC9 passes; F6 cold start feels designed |
| **H9–11** | Artifact viewer: sandboxed iframe, CSP, markdown sanitizer, preview/source toggle, copy and download | AC8 passes |
| **H11–14** | Ship 30 skill: outline JSON → per-section generation → deterministic assembly → validator → bounded repair. Staged progress UI | AC7 passes across 3 runs |
| **H14–16** | Resilience across all five failure modes; structured logging with `trace_id`; `/health/deps` | AC10, AC11, AC12 pass |
| **H16–18** | Automated tests (API, retrieval, routing, persistence) + manual UI test plan | Suite green inside Compose |
| **H18–21** | README, this PRD finalized, `design.md`, `architecture.md`, redacted agent transcripts committed | Fresh-clone rehearsal → AC1 passes |
| **H21–23** | Demo video: problem → product → local Ollama on screen → the §7.1 language-boundary trade-off | Uploaded |
| **H23–24** | Buffer | — |

**Sequencing rationale.** The eval set is written *before* the pipeline so quality is measured rather than felt. The query rewriter lands in H3–5 rather than later because F1 appears to work on turn one without it and fails on turn three with it missing — the most expensive kind of late discovery. Ship 30 (H11–14) is the highest-scoring single block; if the schedule slips, frontend polish is cut to protect it, never the reverse.

---

## 11. Open questions for the client

1. Should the corpus refresh on a schedule, and at what cadence? The ingest is scripted and idempotent; only the trigger is unbuilt.
2. Does the team need shared sessions, or is per-person history sufficient? This determines whether auth moves in-scope next.
3. Are there house style requirements for generated artifacts beyond the Ship 30 format?
4. Is cloud inference permitted for production use, or must all inference remain local? This determines whether §7.5's no-silent-failover stance should harden into a build-time exclusion of the cloud provider entirely.
