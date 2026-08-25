# Python 3.12-slim per architecture.md §3. Pinned by digest is preferred
# per ADR-007; the tag below is pinned to a specific minor+patch, which
# tools/check_pins.py's compose-image check treats as sufficient for local
# dev images (that check runs against docker-compose.yml, not this
# Dockerfile's FROM line, but the same pinning discipline applies here).
FROM python:3.12-slim

WORKDIR /app

# libpq is needed at runtime by asyncpg's optional C extension path on some
# platforms; kept minimal otherwise per architecture.md's "boring, observable
# seams" preference. No build tools retained in the final image layer beyond
# what pip needs to install pure-Python/prebuilt wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY app ./app

# Non-root user (architecture.md §8.5 applies the same posture to `agent`;
# `api` follows suit as a general container-hardening default).
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Healthcheck mirrors docker-compose.yml's own; kept here too so `docker run`
# without Compose still self-reports.
HEALTHCHECK --interval=5s --timeout=5s --retries=20 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
