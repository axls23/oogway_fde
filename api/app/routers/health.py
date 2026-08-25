"""GET /health (pure liveness), GET /health/deps, GET /config.

api/CLAUDE.md: "GET /health never touches the database or Ollama —
liveness only. GET /health/deps checks all three independently and never
raises." AC12 depends on /health/deps reporting db/ollama/agent
independently even when every one of them is down.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Chunk, Episode
from app.db.session import get_db
from app.errors import ApiError
from app.obs.logging import log_event
from app.obs.tracing import new_trace_id
from app.schemas import CapabilitiesOut, ConfigResponse, CorpusStats, DepStatus, HealthDeps

router = APIRouter()

_EMPTY_CAPABILITIES = CapabilitiesOut(
    skills=[], extensions=[], extensions_enabled=False, tools=[], agent_reachable=False
)


@router.get("/health")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


async def _check_db(db: AsyncSession) -> DepStatus:
    try:
        await db.execute(select(1))
        return "ok"
    except SQLAlchemyError:
        return "down"


async def _check_ollama(settings: Settings) -> DepStatus:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            return "ok" if resp.status_code == 200 else "degraded"
    except httpx.HTTPError:
        return "down"


async def _check_agent(settings: Settings) -> DepStatus:
    url = f"{settings.agent_base_url.rstrip('/')}/healthz"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            return "ok" if resp.status_code == 200 else "degraded"
    except httpx.HTTPError:
        return "down"


@router.get("/health/deps", response_model=HealthDeps)
async def health_deps(
    db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings)
) -> HealthDeps:
    trace_id = new_trace_id()
    db_status = await _check_db(db)
    ollama_status = await _check_ollama(settings)
    agent_status = await _check_agent(settings)
    result = HealthDeps(db=db_status, ollama=ollama_status, agent=agent_status)
    log_event("health_deps", trace_id, **result.model_dump())
    return result


async def _fetch_agent_capabilities(settings: Settings, trace_id: str) -> CapabilitiesOut:
    """Best-effort enrichment, not a dependency check — a slow/unreachable
    agent degrades this one field to an empty, explicitly-flagged snapshot
    rather than failing /config itself (the UI still needs provider/model/
    corpus even if the agent is momentarily down). Always logged, never a
    bare except: this is a status field going stale, not a silent failover
    of anything safety-relevant like model provider (ADR-005 is unrelated
    to this)."""
    url = f"{settings.agent_base_url.rstrip('/')}/capabilities"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                log_event(
                    "config_capabilities_degraded", trace_id, level=30, status_code=resp.status_code
                )
                return _EMPTY_CAPABILITIES
            body = resp.json()
            return CapabilitiesOut(
                skills=body.get("skills", []),
                extensions=body.get("extensions", []),
                extensions_enabled=body.get("extensionsEnabled", False),
                tools=body.get("tools", []),
                agent_reachable=True,
            )
    except httpx.HTTPError as exc:
        log_event("config_capabilities_unreachable", trace_id, level=30, error=str(exc))
        return _EMPTY_CAPABILITIES


@router.get("/config", response_model=ConfigResponse)
async def get_config(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ConfigResponse:
    trace_id = new_trace_id()
    try:
        episode_count = (await db.execute(select(func.count()).select_from(Episode))).scalar_one()
        chunk_count = (await db.execute(select(func.count()).select_from(Chunk))).scalar_one()
    except SQLAlchemyError as exc:
        log_event("config_db_error", trace_id, level=40, error=str(exc))
        raise ApiError(503, "DB_UNREACHABLE", "database unreachable", trace_id=trace_id) from exc

    capabilities = await _fetch_agent_capabilities(settings, trace_id)

    return ConfigResponse(
        provider=settings.llm_provider,
        model=settings.llm_model,
        cloud_available=settings.cloud_available,
        corpus=CorpusStats(episode_count=episode_count, chunk_count=chunk_count),
        capabilities=capabilities,
    )
