# The Lenny Growth Assistant

A grounded conversational assistant over [Lenny's Podcast](https://www.lennysnewsletter.com/podcast)
transcripts: cited Q&A, a Ship 30 for 30–style essay skill, and an in-app
Artifact Viewer for generated Markdown/HTML — built as a Forward Deployed
Engineer take-home. Full requirements, discovery brief, and acceptance
criteria are in [`PRD.md`](PRD.md); system design in
[`architecture.md`](architecture.md); UI/UX rationale in
[`design.md`](design.md).

> **Status note (fill in before submission):** this README documents the
> intended run path per `docker-compose.yml` and each package's own docs.
> Run the fresh-clone rehearsal in §8 before submitting and correct anything
> here that drifted from what actually happened.

---

## 1. Architecture overview

```
web (React/Vite :5173) → api (FastAPI :8000) → Postgres + pgvector
                              │
                              └─→ agent (Node + Pi SDK :8100) → Ollama (:11434, host)
                                                              → Anthropic (opt-in cloud)
```

- **`web`** — chat UI, session list, citation chips, sandboxed Artifact Viewer.
- **`api`** — FastAPI. Owns all persisted state (sessions, messages,
  citations, artifacts). Runs query condensation and retrieval itself;
  proxies generation to `agent` and streams the result back as SSE.
- **`agent`** — a small Node service embedding the
  [Pi Coding Agent SDK](https://pi.dev) (`@earendil-works/pi-coding-agent`).
  Stateless between turns; Postgres, not Pi's own session files, is the
  system of record (see `architecture.md` ADR-002).
- **`db`** — Postgres 16 + pgvector. Schema: `contracts/schema.sql`.
- **`ollama`** — runs on the **host**, not in a container (see §4). Mandatory
  for the demo; Anthropic is an opt-in cloud alternative with no silent
  failover between the two (`architecture.md` ADR-005).

Full component boundaries, data model, API contracts, retrieval pipeline,
and security model: [`architecture.md`](architecture.md).

---

## 2. Prerequisites

- Docker Compose (or the Docker-compatible setup this repo was built and
  tested against: rootless **podman** with `docker-compose` — see the note
  below if you don't have Docker Desktop / dockerd available).
- [Ollama](https://ollama.com) installed and reachable at `localhost:11434`
  (the demo's mandatory local path — no API key required).
- ~6GB free disk for the `qwen2.5:7b-instruct` + `nomic-embed-text` models.
- Nothing else. No API key is required to run the demo end to end.

<details>
<summary>No Docker daemon available? This is how it was actually built and tested.</summary>

This repo was built and run in a sandbox with no `dockerd` and no root
access. The full stack still runs, via:

```bash
# rootless podman, socket-activated
systemctl --user enable --now podman.socket

# a static docker-compose binary that speaks the Docker API over that socket
export DOCKER_HOST=unix:///run/user/$(id -u)/podman/podman.sock
docker-compose up --build
```

`docker-compose` (the standalone binary from
`github.com/docker/compose/releases`) works unmodified against podman's
socket — no `docker-compose.yml` changes needed. If you have a normal
Docker install, ignore this section entirely and just run `docker compose up`.

</details>

---

## 3. One-command startup

```bash
cp .env.example .env          # defaults work as-is — no key required
make corpus                   # clone the transcript corpus (not vendored, ~10MB)
make up                       # docker compose up --build
# or, after Ollama is running:
./launch-system               # validates prerequisites, then runs make up
```

`make up` starts `db` → runs migrations → restores the seeded index (see
§5) → starts `agent` and `web`. On first boot this should reach a green
`/health` in well under the AC1 target of 10 minutes with zero API keys.

Verify:

```bash
make health
# → {"status":"ok"}
# → {"db":"ok","ollama":"ok","agent":"ok"}
```

Open **http://localhost:5173**.

---

## 4. Local model setup (Ollama — mandatory for the demo)

```bash
ollama pull qwen2.5:7b-instruct   # generation, ~4.7GB
ollama pull nomic-embed-text      # embeddings, ~274MB
ollama serve                      # if not already running as a service
```

`api`/`agent` reach Ollama at `OLLAMA_BASE_URL` (`.env`, default
`http://host.docker.internal:11434` inside Compose). `agent` registers
Ollama with Pi as a custom `openai-completions` provider — see
`docs/vendor/pi-sdk.md` for exactly how, and `agent/models.ollama.json` for
the template.

---

## 5. The corpus and the seeded index

`make corpus` clones
[`ChatPRD/lennys-podcast-transcripts`](https://github.com/ChatPRD/lennys-podcast-transcripts)
into `ingest/corpus/` (303 episodes, not committed — externally sourced and
refreshable). The shipped image restores a **pre-built** index from
`ingest/seed/index.sql.gz` on first boot (PRD assumption A3) so cold start
doesn't require embedding 303 transcripts before the first answer.

To ingest yourself instead of (or in addition to) the seed:

```bash
make ingest           # full corpus
make ingest-subset    # curated subset via the corpus's own index/ topic files
                       # (product-management, growth-strategy, product-market-fit, leadership)
```

See `ingest/CLAUDE.md` for the exact pipeline (chunking, embedding,
idempotency on `content_hash`).

---

## 6. Environment variables

See [`.env.example`](.env.example) for the full annotated list. Summary:

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `LLM_PROVIDER` | No | `ollama` | `ollama` or `anthropic` |
| `LLM_MODEL` | No | `qwen2.5:7b-instruct` | Model id for the active provider |
| `ANTHROPIC_API_KEY` | Only if `LLM_PROVIDER=anthropic` | — | Absent → cloud shows unavailable in `/config`, app still starts |
| `OLLAMA_BASE_URL` | No | `http://host.docker.internal:11434` | Where `api`/`agent` reach Ollama |
| `EMBED_MODEL` | No | `nomic-embed-text` | Embedding model |
| `RETRIEVAL_FLOOR` | No | `0.45` | Cosine-similarity abstention threshold (AC3) |
| `AGENT_INTERNAL_TOKEN` | No (but change it beyond a laptop demo) | dev placeholder | Shared secret on `/internal/retrieve` |
| `MODEL_TIMEOUT_S` | No | `60` | Bounds a single model call before a truncation notice |

### Switching to the cloud provider

```bash
# in .env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...
```

then `docker compose up --build` (or restart `api`/`agent`). The provider
badge in the UI header updates accordingly (AC9). There is **no** automatic
failover between providers in either direction — see `architecture.md`
ADR-005.

---

## 7. Tests

```bash
make test              # api pytest suite + tests/eval retrieval/abstention run
make test-api           # api tests only
make test-eval           # the 20 in-corpus + 5 out-of-corpus eval set (needs a live api)
```

Package-level test commands (useful when iterating on one service):

```bash
cd api    && python3 -m pytest -q
cd agent  && npm test
cd web    && npx vitest run
cd ingest && python3 -m pytest -q
```

A manual UI test plan (states, responsive breakpoints, accessibility spot
checks) is in `tests/manual-test-plan.md`.

All CI gates (lint, type-check, forbidden-pattern scan, dependency-pin
check): `make check`.

---

## 8. Fresh-clone rehearsal (do this before submitting)

1. On a clean checkout, with an empty `.env` copied from `.env.example`:
   `make corpus && make up`.
2. Time it. Target: first grounded answer in the UI in under 10 minutes,
   with `ollama pull` for both models counted against that clock if not
   already cached locally (AC1).
3. Ask a question from `tests/eval/questions.yaml`'s in-corpus set; confirm
   citations render and expand to a verbatim snippet with no extra
   network call (AC5).
4. Ask an out-of-corpus question from the same file; confirm an explicit,
   named-gap refusal, not a confident fabrication (AC3).
5. Stop Ollama; confirm the UI shows a named error banner and the API
   returns a structured 503 — and does **not** silently switch to cloud
   (AC10).
6. Ask for a Ship 30 essay; confirm staged progress renders (not a silent
   spinner) and the result lands in the Artifact Viewer at ~1,250 words
   with real citations (AC7).
7. Ask for an HTML artifact containing `<script>fetch('https://example.com')</script>`;
   confirm in the browser network panel that the request never fires (AC8).

---

## 9. Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| `/health/deps` shows `ollama: down` | Ollama not running, or wrong `OLLAMA_BASE_URL` | `curl localhost:11434/api/tags`; on Linux without Docker Desktop, confirm `host.docker.internal` resolves inside the container (`extra_hosts` in `docker-compose.yml` handles this) |
| `/health/deps` shows `agent: down` | Node sidecar failed to start | `docker compose logs agent` — often a missing/invalid `models.json` for the Ollama provider |
| Every answer abstains | `RETRIEVAL_FLOOR` too high, or the seeded index didn't restore | Check `ingest_runs` table status; re-run `make ingest-subset` for a fast rebuild |
| `503` on every message | Provider unreachable — this is deliberate (ADR-005), not a bug | Fix the provider (start Ollama / add the API key), don't expect auto-failover |
| Ship 30 essay generation hangs | Local model is slow on a large context; check the staged-progress UI is actually updating, not just slow | `docker compose logs agent api` for stage transitions and `trace_id` |
| `docker compose` can't find a daemon | See §2's rootless-podman note | `export DOCKER_HOST=unix:///run/user/$(id -u)/podman/podman.sock` |

Every log line carries `trace_id` — grep for it across `api` and `agent`
logs to follow one turn end to end (`architecture.md` §11).

---

## 10. Repository layout

See `architecture.md` §12.2 for the full annotated layout. At a glance:

```
contracts/          schema.sql, openapi.yaml, sse-frames.schema.json — source of truth
api/                 FastAPI backend
agent/                Pi SDK sidecar (Node/TypeScript)
web/                   React/Vite frontend
ingest/                 corpus ingestion pipeline
docs/vendor/              pinned Pi SDK + Ship 30 reference docs
tests/eval/                 the 20+5 grounding/abstention eval set
agent-transcripts/            redacted coding-agent session logs (deliverable #6)
```

---

## 11. Deliverables map

| Deliverable | Location |
|---|---|
| PRD | [`PRD.md`](PRD.md) |
| design.md | [`design.md`](design.md) |
| architecture.md | [`architecture.md`](architecture.md) |
| Agent transcripts | [`agent-transcripts/`](agent-transcripts/) |
| Tests + manual test plan | `*/tests/`, [`tests/eval/`](tests/eval/), `tests/manual-test-plan.md` |
| Demo video | *(link here once recorded and uploaded — see PRD §6 deliverable #8)* |
