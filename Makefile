.PHONY: up down logs health corpus ingest ingest-subset seed check test test-api test-eval fmt clean

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

test: test-api test-eval

test-api:
	cd api && python3 -m pytest -q

test-eval:
	cd tests/eval && python3 run_eval.py

fmt:
	cd api && ruff format .
	cd agent && npx biome format --write .
	cd web && npx biome format --write .

clean:
	docker compose down -v
