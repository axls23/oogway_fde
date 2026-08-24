# api/ — FastAPI backend

Governing contracts: `../contracts/schema.sql`, `../contracts/openapi.yaml`,
`../contracts/sse-frames.schema.json`. Root invariants in `../CLAUDE.md`
apply here without exception — this package is where most of them are
enforced in code (relevance floor, citation construction, no silent
failover).

## Structure

```
app/
  main.py            FastAPI app, router registration, startup (migrations, dep checks)
  config.py           Settings from env, matching .env.example exactly
  db/
    models.py         SQLAlchemy models mirroring contracts/schema.sql exactly
    migrations/        Alembic
  routers/
    sessions.py        /sessions, /sessions/{id}, /sessions/{id}/messages
    health.py          /health, /health/deps, /config
    artifacts.py        /artifacts/{id}, /chunks/{id}
    internal.py         /internal/retrieve (shared-secret guarded)
  services/
    condense.py         query condensation (one low-temp call, both forms logged)
    retrieval.py         embed -> top-k -> session boost -> relevance floor -> top 4
    agent_client.py       HTTP client to the agent service, SSE passthrough
    sanitize.py           markdown sanitizer (allowlisted tags), HTML pass-through prep
    ship30.py              outline -> per-section calls -> deterministic assembly -> validator -> bounded repair
  obs/
    logging.py            structured JSON logs, one line per stage, trace_id everywhere
    tracing.py             trace_id generation/propagation
tests/
requirements.txt        exact pins, no ranges
```

## Non-negotiable behaviors

- `retrieval.py`'s relevance floor is a plain `if max_score < RETRIEVAL_FLOOR:`
  guard that short-circuits *before* any model call — not a prompt
  instruction anywhere. This is what AC3 tests.
- Citations attached to a message are built from the ranked chunk list
  `internal/retrieve` returns, keyed by chunk_id the agent echoes back —
  never parsed out of the model's text.
- `/sessions/{id}/messages` streams the exact SSE frame shapes in
  `contracts/sse-frames.schema.json`. Validate outgoing frames against it
  in tests, not just by eyeballing.
- If `ANTHROPIC_API_KEY` is absent and `LLM_PROVIDER=anthropic` is
  requested at runtime, return the structured 503 — do not crash at
  startup and do not silently use Ollama instead.
- Every exception handler logs with `trace_id` before returning the
  `ErrorEnvelope` shape from `contracts/openapi.yaml`. No bare `except:`.
- `GET /health` never touches the database or Ollama — liveness only.
  `GET /health/deps` checks all three independently and never raises.

## Commands

```
pip install -r requirements.txt
ruff check . && mypy --strict app
python -m pytest -q
uvicorn app.main:app --reload --port 8000
```
