"""embed_query(), mocked at the HTTP boundary (no live Ollama call, no DB).

Covers the search_query: prefix (Nomic's asymmetric-retrieval task
instruction for the query side) applied to the string actually sent to
Ollama's embeddings endpoint, while leaving the caller's `query` untouched
-- that's the same string retrieve() logs and, upstream, what ends up in
messages.rewritten_query.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.services import retrieval as retrieval_module

TRACE = "test-trace"


def _settings(**overrides: Any) -> Settings:
    return Settings(
        ollama_base_url="http://127.0.0.1:9-not-used",
        **overrides,
    )


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.last_body: dict[str, Any] | None = None

    def __call__(self, *a: Any, **kw: Any) -> _FakeAsyncClient:
        return self

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.last_body = json
        return _FakeResponse({"embedding": [0.1] * 768})


async def test_embed_query_prefixes_the_sent_prompt_with_search_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAsyncClient()
    monkeypatch.setattr(retrieval_module.httpx, "AsyncClient", fake_client)

    query = "what do guests say about activation?"
    result = await retrieval_module.embed_query(query, _settings(), TRACE)

    assert result == [0.1] * 768
    assert fake_client.last_body is not None
    assert (
        fake_client.last_body["prompt"]
        == f"{retrieval_module.SEARCH_QUERY_PREFIX}{query}"
    )
    # The prefix must never leak into the query string itself -- callers
    # (retrieve()'s logging, messages.rewritten_query upstream) still see
    # the raw condensed query.
    assert query == "what do guests say about activation?"
