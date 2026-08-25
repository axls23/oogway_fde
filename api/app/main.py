"""FastAPI app: router registration, startup (migrations, fail-fast on DB
down), global error handling.

architecture.md §4: "Migrations run through Alembic on api startup, before
the service reports healthy." architecture.md §11 / PRD §7.7: "Database
unavailable at boot: fail fast with a clear message rather than serving a
broken UI" — the lifespan below does exactly that: if migrations can't run
because Postgres isn't reachable, the exception propagates out of the
lifespan context manager and uvicorn exits non-zero instead of serving.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db.session import dispose_engine
from app.errors import ApiError
from app.obs.logging import configure_logging, log_event
from app.obs.tracing import new_trace_id
from app.routers import artifacts, extension_proposals, health, internal, sessions

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _run_migrations_sync() -> None:
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")


async def run_migrations() -> None:
    # alembic's env.py drives its own async engine via asyncio.run(); that
    # can't happen inside the loop that's already running this startup
    # hook, so the sync `command.upgrade` call is pushed to a thread.
    await asyncio.to_thread(_run_migrations_sync)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    trace_id = new_trace_id()
    try:
        await run_migrations()
    except Exception as exc:  # noqa: BLE001 — fail-fast boot path, logged then re-raised, never swallowed
        log_event(
            "startup_migrations_failed",
            trace_id,
            level=logging.CRITICAL,
            error=str(exc),
        )
        raise
    log_event("startup_complete", trace_id)
    yield
    await dispose_engine()


app = FastAPI(title="Lenny Growth Assistant API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(artifacts.router)
app.include_router(internal.router)
app.include_router(extension_proposals.router)


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    log_event(
        "api_error",
        exc.trace_id,
        level=logging.WARNING,
        code=exc.code,
        message=exc.message,
        path=str(request.url.path),
        status_code=exc.status_code,
    )
    return JSONResponse(status_code=exc.status_code, content=exc.to_envelope())


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    trace_id = new_trace_id()
    log_event(
        "unhandled_exception",
        trace_id,
        level=logging.ERROR,
        error=str(exc),
        error_type=type(exc).__name__,
        path=str(request.url.path),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "an unexpected error occurred",
                "trace_id": trace_id,
                "retryable": False,
            }
        },
    )
