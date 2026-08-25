"""embeddings.py, mocked at the HTTP boundary (no live Ollama call).

Covers the search_document: prefix (Nomic's asymmetric-retrieval task
instruction for corpus-side text) applied to the string actually sent to
Ollama's /api/embed, while leaving the caller's input texts untouched --
those are what end up in the stored chunks.text column, which must stay
unprefixed (raw, as shown to users via /chunks/{id} and citations).
"""

from __future__ import annotations

from typing import Any, Self

import pytest

import embeddings as embeddings_module
from embeddings import EMBED_DIMENSIONS, SEARCH_DOCUMENT_PREFIX, OllamaEmbedder


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def __call__(self, *a: Any, **kw: Any) -> _FakeAsyncClient:
        return self

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.requests.append(json)
        vectors = [[0.1] * EMBED_DIMENSIONS for _ in json["input"]]
        return _FakeResponse({"embeddings": vectors})


async def test_embed_many_prefixes_each_text_with_search_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAsyncClient()
    monkeypatch.setattr(embeddings_module.httpx, "AsyncClient", fake_client)

    embedder = OllamaEmbedder(base_url="http://127.0.0.1:11434", model="nomic-embed-text")
    texts = ["first chunk of transcript", "second chunk of transcript"]

    embeddings = await embedder.embed_many(texts)

    assert len(embeddings) == 2
    assert len(fake_client.requests) == 1
    sent_inputs = fake_client.requests[0]["input"]
    assert sent_inputs == [f"{SEARCH_DOCUMENT_PREFIX}{t}" for t in texts]


async def test_embed_many_does_not_mutate_caller_texts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller's list (which ingest.py also uses to build chunk rows for
    the DB) must come back exactly as passed -- unprefixed."""
    fake_client = _FakeAsyncClient()
    monkeypatch.setattr(embeddings_module.httpx, "AsyncClient", fake_client)

    embedder = OllamaEmbedder(base_url="http://127.0.0.1:11434", model="nomic-embed-text")
    texts = ["raw chunk text shown in citations"]

    await embedder.embed_many(texts)

    assert texts == ["raw chunk text shown in citations"]


async def test_embed_many_empty_list_makes_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*a: Any, **kw: Any) -> Any:
        raise AssertionError("embed_many([]) must not call Ollama")

    monkeypatch.setattr(embeddings_module.httpx, "AsyncClient", _boom)

    embedder = OllamaEmbedder(base_url="http://127.0.0.1:11434", model="nomic-embed-text")
    assert await embedder.embed_many([]) == []
