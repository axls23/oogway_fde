# CLAUDE.md — root invariants

This file, and the one in each package (`api/`, `agent/`, `web/`, `ingest/`),
is the mechanism by which the decisions in `architecture.md` survive contact
with a code generator. Read `PRD.md` and `architecture.md` before writing
code in this repository. `contracts/` is the source of truth for schemas and
API shapes — derive code from it, don't invent alongside it.

## Invariants that must never be refactored away

1. **Citations are constructed from retrieval metadata, never parsed from
   model output.** The model writes prose; `api` writes the `citation`
   SSE frames from the ranked chunk list returned by `/internal/retrieve`.
   A model cannot invent a guest name or episode title because it never
   gets to write one into a citation payload. (architecture.md §7)
2. **The relevance floor is enforced in Python, before the model sees
   context.** `RETRIEVAL_FLOOR` is a guard in `api/app/services/retrieval.py`,
   not a system-prompt instruction. This is the mechanism behind AC3.
3. **No silent failover between providers.** If the configured provider is
   unreachable, return a structured `503` with `retryable: true`. Never
   fall back to the other provider automatically. (ADR-005)
4. **The Pi session is created with `noTools: "builtin"`.** Only
   `search_transcripts` and `create_artifact` are available to the model.
   No `read`, `bash`, `edit`, `write`. (§8.5)
5. **The artifact iframe never gains `allow-same-origin`.** `sandbox`
   stays `"allow-scripts"` only. (ADR-004)
6. **Postgres is the only store ever read for application state.** Pi's
   JSONL session files are an audit trail, written but never read back.
   (ADR-002)

## Forbidden patterns

- Bare `except:` / `except Exception:` or `catch {}` that swallows an error
  without logging it (with `trace_id`).
- Silent fallback paths — returning empty results, a default value, or
  switching provider when the intended path failed, without surfacing an
  error to the caller.
- Environment variables used in code but not documented in `.env.example`.
- New dependencies added without them appearing in this commit's diff for
  the relevant `requirements.txt` / `package.json` — no drive-by additions.
- Real credentials, or plausible-looking fake ones, in code, tests, or docs.
- Editing a generated Alembic migration in place rather than adding a new
  one — `contracts/schema.sql` is regenerated from migrations, not the
  reverse.
- Range specifiers (`^`, `~`, `>=`) in `agent/package.json` or `web/package.json`
  dependencies; unpinned base images in Dockerfiles. (ADR-007)

## Where things live

| Concern | Owning file |
|---|---|
| DB schema | `contracts/schema.sql` — Alembic migrations are generated from it |
| API shapes | `contracts/openapi.yaml` |
| SSE frame protocol | `contracts/sse-frames.schema.json` |
| Pi SDK API reference | `docs/vendor/pi-sdk.md` — treat as the only authority; verified against `@earendil-works/pi-coding-agent@0.84.3` on npm, 2026-08-24 |
| Ship 30 writing principles | `agent/.pi/skills/ship30-essay/SKILL.md` |

## Commands

`make up` starts everything. `make check` runs every CI gate. `make test`
runs the automated test suite plus the retrieval/abstention eval. See the
root `Makefile` for the full list.
