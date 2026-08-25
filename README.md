# The Lenny Growth Assistant

A grounded conversational assistant over [Lenny's Podcast](https://www.lennysnewsletter.com/podcast)
transcripts: cited Q&A, a Ship 30 for 30–style essay skill, and an in-app viewer for
generated Markdown/HTML. Runs entirely on a local 7B model — no API key required.

This README is deliberately short: **how to run it**, and **where to read about it**.
Everything else lives in the documents mapped in §4.

---

## 1. Run it

**You need:** Docker (or rootless podman — the script handles either),
[Ollama](https://ollama.com), and ~6GB of disk for the two models.

```bash
./launch-system        # does everything below, and checks each step
make ingest-subset     # populate the corpus — see the note, this is required
```

Then open **http://localhost:5173**.

`./launch-system` copies `.env` from `.env.example`, clones the transcript corpus,
finds a working Compose entry point, starts Ollama **bound to `0.0.0.0`** so containers
can actually reach it, pulls `qwen2.5:7b-instruct` and `nomic-embed-text`, brings up
the four services, and waits for `db`, `ollama` and `agent` to all report healthy.
It is idempotent — safe to re-run.

> **The ingest step is not optional.** A fresh database starts with zero episodes, and
> until one ingest has run, *every* question will correctly abstain with "outside the
> corpus." `ingest/seed/index.sql.gz` ships a pre-built index, but nothing currently
> restores it on boot — see §5. `make ingest-subset` covers four curated topics and is
> the fast path; `make ingest` does all 303 episodes (~8,531 chunks; 1 fails to parse).

Stop with `docker compose down`. Logs: `docker compose logs -f`.

---

## 2. Check it works

```bash
make health
# → {"status":"ok"}
# → {"db":"ok","ollama":"ok","agent":"ok"}
```

Four things worth trying in the UI, each demonstrating a guarantee the system makes
in code rather than in a prompt:

| Try this | You should see | Guarantee |
|---|---|---|
| An in-corpus question (see `tests/eval/questions.yaml`) | Citation chips that expand to the **verbatim** transcript snippet, instantly and with no extra model call | Citations are built from retrieval metadata, never parsed from model text |
| An out-of-corpus question (same file, `out_of_corpus` set) | A calm "outside the corpus" card naming the gap — not a confident fabrication, and not styled as an error | A relevance floor enforced in Python *before* the model is called |
| Stop Ollama, then ask anything | A named error banner and a structured `503` — and **no** silent switch to a cloud provider | No silent failover between providers |
| Ask for a Ship 30 essay | Staged progress ("Drafting section 3 of 6…"), not a silent spinner, landing in the artifact pane | The multi-call pipeline is shown honestly rather than hidden |

On CPU-only hardware a full turn routinely takes 120–200s. If you see timeouts, raise
`MODEL_TIMEOUT_S` in `.env` — `launch-system` warns about this when it finds no GPU.

---

## 3. Tests

```bash
make test     # api suite + the 20 in-corpus / 5 out-of-corpus eval set
make check    # all CI gates: lint, type-check, forbidden patterns, dependency pins
```

A manual UI test plan (states, breakpoints, accessibility) is in `tests/manual-test-plan.md`.

---

## 4. Reviewer's guide to the documents

**If you have fifteen minutes**, read these three things in this order:

1. [`docs/deliverables/architecture.md`](docs/deliverables/architecture.md) **§0 → §2.1** —
   the diagram index, then the end-to-end turn sequence. That one sequence diagram is
   the spine of the whole system.
2. [`docs/deliverables/design.md`](docs/deliverables/design.md) **§1** — a table mapping
   each backend guarantee to the one UI element that makes it visible to a
   non-technical user. It explains why the interface looks the way it does.
3. [`CLAUDE.md`](CLAUDE.md) — the invariants that must survive contact with a code
   generator, each stated with its reason.

**The full map:**

| Document | What it answers | Where to start |
|---|---|---|
| [`docs/deliverables/PRD.md`](docs/deliverables/PRD.md) | Who this is for, which flows matter, what "done" means | §1 personas, §6 flows and acceptance criteria |
| [`docs/deliverables/architecture.md`](docs/deliverables/architecture.md) | How it's built and why those seams | §0 diagram index — 9 diagrams, each labelled with the files it covers |
| [`docs/deliverables/design.md`](docs/deliverables/design.md) | Why the UI is shaped this way | §1 backend guarantee → interface |
| [`contracts/`](contracts/) | Source of truth for schema, API and SSE frames — code is derived from these, not written alongside them | `schema.sql` |
| [`CLAUDE.md`](CLAUDE.md) + per-package `CLAUDE.md` | The invariants and forbidden patterns constraining every change | Invariants list |
| [`docs/vendor/pi-sdk.md`](docs/vendor/pi-sdk.md) | Pinned Pi SDK reference — treated as the only authority for that API | — |

The three questions a reviewer usually asks first, and where `architecture.md` settles each:

- *Can the model fabricate a citation?* No — §7, and the trust-boundary diagram in §10.
  It writes prose and never writes into a citation payload.
- *What stops a prompt injection in a transcript from doing damage?* §8.5 and §10.1 —
  the session has no filesystem or shell tool it could be talked into using.
- *Why is generated HTML safe to render?* ADR-004 — a sandboxed iframe that is never
  granted `allow-same-origin`.

---

## 5. Known gaps

- **No seed-restore path.** `ingest/seed/index.sql.gz` (43MB, a plain `pg_dump`) is
  mounted into the `api` container but nothing restores it, and Alembic has already
  created the tables by the time it could. So cold start requires a real ingest, which
  is what `launch-system` tells you. Closing this is what the "first answer in under
  10 minutes" target depends on.
- **Agent transcripts.** `agent-transcripts/` exists but is empty; the redacted
  coding-agent session logs still need to be exported into it.
- **Demo video** — *(link here once recorded)*.

---

## 6. Configuration

Defaults work as-is. [`.env.example`](.env.example) is the annotated list — it is the
only place to look, and every variable used in code appears there.

To use the cloud provider instead of local: set `LLM_PROVIDER=anthropic`,
`LLM_MODEL=claude-sonnet-4-5` and `ANTHROPIC_API_KEY` in `.env`, then restart.
The provider badge in the UI header reflects whichever is active. There is no
automatic failover in either direction, by design.

---

## 7. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Every answer abstains | No ingest has run yet. `make ingest-subset`. Confirm with `curl localhost:8000/config`. |
| `/health/deps` shows `ollama: down` while `curl localhost:11434` works from your shell | Ollama is bound to `127.0.0.1` and containers can't reach it. Restart it as `OLLAMA_HOST=0.0.0.0:11434 ollama serve` — this is the single most common failure. |
| `/health/deps` shows `agent: down` | `docker compose logs agent` — usually an invalid `agent/models.ollama.json` for the Ollama provider. |
| `503` on every message | The configured provider is unreachable. This is deliberate, not a bug — fix the provider; there is no auto-failover. |
| No Docker daemon | `launch-system` falls back to rootless podman's Docker-API socket automatically. Manually: `export DOCKER_HOST=unix:///run/user/$(id -u)/podman/podman.sock`. |

Every log line carries a `trace_id`; grep it across `api` and `agent` logs to follow a
single turn across both runtimes.
