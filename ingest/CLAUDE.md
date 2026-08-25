# ingest/ — corpus ingestion

Governed by `../contracts/schema.sql` alone — no API contract involved.
Reads `corpus/` (the cloned `ChatPRD/lennys-podcast-transcripts` repo, not
committed — see `make corpus`), writes directly to Postgres via the same
connection string `api` uses.

## Structure

```
ingest.py        CLI: parse frontmatter -> chunk -> embed -> upsert, idempotent on content_hash
chunker.py         fixed-size ~800 tokens, 15% overlap, split on speaker turns where present
seed/index.sql.gz   pre-built dump restored on first `api` boot (AC1) — see ../Makefile `make seed`
```

## Non-negotiable behaviors

- Idempotent: an unchanged `content_hash` for a `source_path` is skipped
  entirely, not re-embedded. A changed hash deletes and replaces that
  episode's chunks via cascade, then re-inserts.
- Every episode row's `source_path` and `youtube_url` must be populated
  when present in frontmatter — this is the traceability contract
  (architecture.md §6, "any sentence in any answer can be walked back...").
- Malformed transcripts are logged and skipped, counted in `ingest_runs`;
  the run continues rather than aborting (resilience requirement, §5.11).
- Each transcript body is `SPEAKER NAME (HH:MM:SS):` per turn, confirmed
  consistent across the corpus (verified 2026-08-24, corrects PRD A8).
  Parse these markers and stamp each chunk with `start_seconds` from the
  nearest preceding turn marker — this is what lets a citation deep-link
  to `youtube_url + "&t=" + start_seconds + "s"`.
- Embeddings come from Ollama's `nomic-embed-text` (768-d) — matches
  `vector(768)` in `contracts/schema.sql` exactly. If that dimension
  changes, the schema and this code change together, not independently.
- `--episodes subset` selects via the corpus repo's own `index/` topic
  files (product management, growth strategy, PMF, leadership) per PRD §5's
  conditional scope cut — document in the ingest log which set ran.
- `embeddings.py` prepends Nomic's `"search_document: "` task-instruction
  prefix to each chunk's text before it's sent to Ollama's `/api/embed` —
  the corpus side of nomic-embed-text's documented asymmetric-retrieval
  convention (query side: `api/app/services/retrieval.py`'s
  `"search_query: "` prefix on `embed_query()`). The prefix is applied only
  to the string handed to the embedding call; `chunks.text` in Postgres,
  and everything downstream of it (citations, `/chunks/{id}`), stays raw
  and unprefixed.
  **This is a chunk-text-preprocessing change, and like any such change it
  only takes effect for embeddings computed after it ships.** Existing rows
  — including everything in `seed/index.sql.gz` — were embedded without the
  prefix, so on any deployment that already has data, mixing prefixed
  queries against an unprefixed (or partially prefixed) index degrades
  retrieval instead of improving it: **a full re-ingest (`make ingest`,
  or `python3 ingest.py --episodes all`) is required before this — or any
  future chunk-preprocessing change — takes effect.** `seed/index.sql.gz`
  itself must be regenerated from a from-scratch ingest run for new
  environments to pick up the prefix too; until it's regenerated, treat it
  as stale.

## Commands

```
python3 ingest.py --episodes all      # full corpus
python3 ingest.py --episodes subset   # curated subset
python3 ingest.py --episodes 10       # first N, for a fast local smoke test
```
