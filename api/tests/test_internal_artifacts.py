"""POST/PATCH /internal/artifacts — the agent's create_artifact/edit_artifact
write path (contracts/openapi.yaml, routers/internal.py).

PATCH is the interesting case here: it must revise the row in place and it
must refuse to touch an artifact that belongs to a different session, even
though both requests carry a valid shared internal token — the token proves
"this is the agent service," not "this call is scoped to this session."
"""

from __future__ import annotations

import os

from httpx import AsyncClient

INTERNAL_TOKEN = os.environ["AGENT_INTERNAL_TOKEN"]


async def _create_session(app_client: AsyncClient) -> str:
    resp = await app_client.post("/sessions", json={"title": "Artifact edit test"})
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_create_then_edit_artifact_round_trip(app_client: AsyncClient) -> None:
    session_id = await _create_session(app_client)

    created = await app_client.post(
        "/internal/artifacts",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        json={"session_id": session_id, "kind": "markdown", "title": "Memo v1", "content": "# v1"},
    )
    assert created.status_code == 201
    artifact_id = created.json()["id"]
    assert created.json()["content"] == "# v1"

    edited = await app_client.patch(
        f"/internal/artifacts/{artifact_id}",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        json={"session_id": session_id, "title": "Memo v2", "content": "# v2, revised"},
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["id"] == artifact_id
    assert body["title"] == "Memo v2"
    assert body["content"] == "# v2, revised"
    assert body["kind"] == "markdown"  # edit never changes kind

    fetched = await app_client.get(f"/artifacts/{artifact_id}")
    assert fetched.status_code == 200
    assert fetched.json()["content"] == "# v2, revised"


async def test_edit_artifact_wrong_session_is_not_found(app_client: AsyncClient) -> None:
    owning_session = await _create_session(app_client)
    other_session = await _create_session(app_client)

    created = await app_client.post(
        "/internal/artifacts",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        json={"session_id": owning_session, "kind": "markdown", "title": "Memo", "content": "# v1"},
    )
    artifact_id = created.json()["id"]

    resp = await app_client.patch(
        f"/internal/artifacts/{artifact_id}",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        json={"session_id": other_session, "content": "attacker-controlled content"},
    )
    assert resp.status_code == 404

    unchanged = await app_client.get(f"/artifacts/{artifact_id}")
    assert unchanged.json()["content"] == "# v1"


async def test_edit_artifact_missing_id_is_not_found(app_client: AsyncClient) -> None:
    session_id = await _create_session(app_client)
    resp = await app_client.patch(
        "/internal/artifacts/00000000-0000-0000-0000-000000000000",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        json={"session_id": session_id, "content": "x"},
    )
    assert resp.status_code == 404


async def test_edit_artifact_bad_token_is_unauthorized(app_client: AsyncClient) -> None:
    session_id = await _create_session(app_client)
    created = await app_client.post(
        "/internal/artifacts",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        json={"session_id": session_id, "kind": "markdown", "title": "Memo", "content": "# v1"},
    )
    artifact_id = created.json()["id"]

    resp = await app_client.patch(
        f"/internal/artifacts/{artifact_id}",
        headers={"X-Internal-Token": "wrong"},
        json={"session_id": session_id, "content": "x"},
    )
    assert resp.status_code == 401
