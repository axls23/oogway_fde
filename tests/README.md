# Tests — a reviewer's index

Tests live next to the code they cover, so this folder holds the two things
that belong to no single package (the retrieval eval and the manual UI plan)
plus this map. **Start here, not by opening 200 test files.**

```bash
make test        # api + agent + web + ingest — no live Ollama or stack needed
make test-eval   # retrieval/abstention eval — needs a running api AND Ollama
```

`make test-api` starts an ephemeral Postgres on :5433 automatically (the DB
tests run against a real pgvector instance rather than mocking the database
away) and tears it down afterwards. Docker is the only prerequisite.

## Where each suite lives

| Suite | Count | Owns |
|---|---|---|
| `api/tests/` | 92 | Endpoint contracts, retrieval scoring, the relevance floor, SSE frame shapes, sanitisation, persistence and cascade |
| `agent/tests/` | 42 | Pi event → wire frame mapping, the three tools' HTTP behaviour, the fail-closed extension manifest |
| `web/src/**/*.test.*` | 48 | SSE parsing, turn state machine, citation chip, abstention card, error banner, artifact sandboxing |
| `ingest/tests/` | 35 | Chunking, embedding prefixes, re-ingest idempotency, transcript parsing |
| `tests/eval/` | 25 questions | 20 in-corpus + 5 out-of-corpus, scored end to end (AC2, AC3) |
| `tests/manual-test-plan.md` | 10 sections | What automation can't check: how the UI looks and behaves |

## If you only read five tests

These are the ones carrying the guarantees the whole design rests on.

| Guarantee | Test |
|---|---|
| A below-floor question never reaches the model at all (AC3) | `api/tests/test_api_routing.py::test_below_floor_turn_abstains_without_ever_calling_the_agent` — deliberately omits the fake-agent fixture, so a regression that starts calling the model fails loudly instead of quietly answering |
| Citations are built from retrieval metadata, never model prose | `api/tests/test_api_routing.py::test_internal_retrieve_returns_ranked_chunks_with_metadata` — guest and episode come from the DB join |
| Fusion can reorder citations but can never rescue a turn that should abstain | `api/tests/test_retrieval_floor.py::test_floor_ranked_override_reorders_selection_but_not_the_abstain_decision` |
| The artifact iframe never gains `allow-same-origin` (ADR-004) | `web/src/components/ArtifactViewer/sandboxHtml.test.ts` |
| An unapproved Pi extension fails session construction rather than loading | `agent/tests/capabilities.test.ts::verifyExtensions: fail-closed on an extension not listed in the manifest` |

## Two things worth knowing

**The DB tests are real.** `api/tests/conftest.py` runs migrations against an
actual pgvector instance and truncates between tests. Nothing about the
database is mocked, so a schema or cascade regression surfaces here rather
than in production.

**Known gap.** ADR-005's "no silent failover between providers" has frontend
coverage (`web/src/components/Chat/ErrorBanner.test.tsx`) but no backend test
asserting that an unreachable provider returns a structured 503 instead of
switching. Worth adding.
