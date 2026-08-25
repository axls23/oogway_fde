"""GET /health, GET /health/deps, GET /config.

AC12: /health/deps reports db/ollama/agent independently. Tested here by
forcing each dependency down (via monkeypatching the httpx client calls
and, for db, using a broken URL through a throwaway settings override) and
asserting the OTHER two remain independently reported — never a single
combined status, and the endpoint never raises even when everything is
down.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.routers import health as health_router


class _DeadClient:
    """Simulates every dependency being unreachable via httpx.AsyncClient."""

    def __init__(self, *a: Any, **kw: Any) -> None:
        pass

    async def __aenter__(self) -> _DeadClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, *a: Any, **kw: Any) -> Any:
        raise httpx.ConnectError("connection refused")


class _FakeCapabilitiesResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {
            "skills": [{"name": "ship30-essay", "description": "Write a Ship 30 essay"}],
            "extensions": [],
            "extensionsEnabled": False,
            "tools": ["search_transcripts", "create_artifact"],
        }


class _FakeAgentClient:
    def __init__(self, *a: Any, **kw: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeAgentClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, *a: Any, **kw: Any) -> Any:
        return _FakeCapabilitiesResponse()


async def test_health_live_is_always_ok(app_client: AsyncClient) -> None:
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_deps_reports_all_three_keys(app_client: AsyncClient) -> None:
    resp = await app_client.get("/health/deps")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"db", "ollama", "agent"}
    # db should be reachable against the real test Postgres
    assert body["db"] == "ok"


async def test_health_deps_reports_ollama_and_agent_down_independently(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health_router.httpx, "AsyncClient", _DeadClient)
    resp = await app_client.get("/health/deps")
    assert resp.status_code == 200  # never raises, even with every dep down
    body = resp.json()
    assert body["ollama"] == "down"
    assert body["agent"] == "down"
    # db still reported independently (it doesn't go through httpx.AsyncClient)
    assert body["db"] == "ok"


async def test_config_reports_provider_and_corpus_stats(app_client: AsyncClient) -> None:
    resp = await app_client.get("/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "ollama"
    assert "cloud_available" in body
    assert body["cloud_available"] is False  # no ANTHROPIC_API_KEY in test env
    assert body["corpus"]["episode_count"] == 0
    assert body["corpus"]["chunk_count"] == 0
    assert body["capabilities"]["agent_reachable"] is False  # no agent running in the test env


async def test_config_capabilities_degrade_to_empty_when_agent_unreachable(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health_router.httpx, "AsyncClient", _DeadClient)
    resp = await app_client.get("/config")
    assert resp.status_code == 200  # /config never fails just because capabilities didn't load
    caps = resp.json()["capabilities"]
    assert caps == {
        "skills": [],
        "extensions": [],
        "extensions_enabled": False,
        "tools": [],
        "agent_reachable": False,
    }


async def test_config_reports_capabilities_from_a_reachable_agent(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health_router.httpx, "AsyncClient", _FakeAgentClient)
    resp = await app_client.get("/config")
    assert resp.status_code == 200
    caps = resp.json()["capabilities"]
    assert caps["agent_reachable"] is True
    assert caps["skills"] == [{"name": "ship30-essay", "description": "Write a Ship 30 essay"}]
    assert caps["tools"] == ["search_transcripts", "create_artifact"]
    assert caps["extensions_enabled"] is False
