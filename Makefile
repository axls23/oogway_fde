.PHONY: up down logs health corpus ingest ingest-subset seed check test test-api \
        test-agent test-web test-ingest test-eval test-db-up test-db-down fmt clean

# One-command startup (AC1). Assumes Ollama is running on the host and
# .env exists (copy from .env.example — the defaults work out of the box).
up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

health:
	curl -sf http://localhost:8000/health && echo
	curl -sf http://localhost:8000/health/deps && echo

# Fetch the corpus (not vendored — large and externally sourced).
corpus:
	git clone --depth 1 https://github.com/ChatPRD/lennys-podcast-transcripts.git ingest/corpus

# Full-corpus ingest (303 episodes, ~8,531 chunks; 1 currently fails to
# parse). Requires db + Ollama reachable.
ingest:
	cd ingest && python3 ingest.py --episodes all

# Curated subset ingest — see PRD §5 conditional scope cut.
ingest-subset:
	cd ingest && python3 ingest.py --episodes subset

# Rebuild the seeded index dump shipped in ingest/seed/index.sql.gz.
seed:
	docker exec -t $$(docker compose ps -q db) \
	  pg_dump -U lenny lenny_growth_assistant | gzip > ingest/seed/index.sql.gz

# All CI gates (architecture.md §12.6), runnable locally.
check:
	cd api && ruff check . && mypy --strict app
	cd agent && npx tsc --noEmit && npx biome check .
	python3 tools/forbidden_patterns.py
	python3 tools/check_pins.py
	python3 tools/check_extension_manifest.py

# Everything runnable without a live Ollama or a running stack. This is the
# target a reviewer should use; test-eval is separate because it needs both.
test: test-api test-agent test-web test-ingest

# api's DB-backed tests run against a REAL ephemeral Postgres (conftest.py:
# not silently skipped or mocked away), so provision one first. Without this
# roughly a third of the api suite errors out on connection refused rather
# than reporting anything useful.
test-api: test-db-up
	@status=0; (cd api && python3 -m pytest -q) || status=$$?; $(MAKE) test-db-down; exit $$status

TEST_DB_CONTAINER := lenny-test-db
TEST_DB_PORT      := 5433

test-db-up:
	@docker inspect $(TEST_DB_CONTAINER) >/dev/null 2>&1 && \
	  echo "test db already running" && exit 0 || true
	@echo "==> starting ephemeral test Postgres on :$(TEST_DB_PORT)"
	@docker run -d --rm --name $(TEST_DB_CONTAINER) \
	  -e POSTGRES_USER=lenny -e POSTGRES_PASSWORD=lenny \
	  -e POSTGRES_DB=lenny_growth_assistant \
	  -p $(TEST_DB_PORT):5432 pgvector/pgvector:pg16 >/dev/null
	@for i in $$(seq 1 60); do \
	  docker exec $(TEST_DB_CONTAINER) pg_isready -U lenny -d lenny_growth_assistant \
	    >/dev/null 2>&1 && exit 0; \
	  sleep 1; \
	done; \
	echo "test db did not become ready" >&2; exit 1

test-db-down:
	@docker rm -f $(TEST_DB_CONTAINER) >/dev/null 2>&1 || true

test-agent:
	cd agent && npm test

test-web:
	cd web && npx vitest run

test-ingest:
	cd ingest && python3 -m pytest -q

# Needs a live api AND a live Ollama — kept out of `make test` so the main
# target stays runnable on a machine with neither.
test-eval:
	cd tests/eval && python3 run_eval.py

fmt:
	cd api && ruff format .
	cd agent && npx biome format --write .
	cd web && npx biome format --write .

clean:
	docker compose down -v
