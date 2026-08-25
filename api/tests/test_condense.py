"""services/condense.py, mocked at the HTTP boundary (no live model call —
see test_condense_integration.py for the real-Ollama version).

Covers the AC4-relevant plumbing: turn 1 skips the model call entirely
(nothing to condense), and a later turn sends the accumulated history to
the provider and returns exactly one line.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.db.models import Message
from app.services import condense as condense_module

TRACE = "test-trace"


def _settings(**overrides: Any) -> Settings:
    return Settings(
        llm_provider="ollama",
        llm_model="qwen2.5:7b-instruct",
        ollama_base_url="http://127.0.0.1:9-not-used",
        **overrides,
    )


def _msg(role: str, content: str) -> Message:
    m = Message(session_id=None, role=role, content=content, trace_id="x")  # type: ignore[arg-type]
    return m


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.last_body: dict[str, Any] | None = None

    def __call__(self, *a: Any, **kw: Any) -> _FakeAsyncClient:
        return self

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.last_body = json
        return _FakeResponse({"message": {"content": self._response_text}})


async def test_turn_one_skips_model_call_entirely(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a: Any, **kw: Any) -> Any:
        raise AssertionError("condense() must not call the model on turn 1")

    monkeypatch.setattr(condense_module.httpx, "AsyncClient", _boom)
    raw, condensed = await condense_module.condense(
        "our activation dropped, what do people say?", [], _settings(), TRACE
    )
    assert raw == "our activation dropped, what do people say?"
    assert condensed == raw


async def test_later_turn_calls_model_with_history_and_returns_one_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAsyncClient("What does B2B activation look like?\nextra line ignored")
    monkeypatch.setattr(condense_module.httpx, "AsyncClient", fake_client)

    history = [
        _msg("user", "our activation dropped after onboarding changes"),
        _msg("assistant", "several guests discuss onboarding friction..."),
    ]
    raw, condensed = await condense_module.condense(
        "what about B2B?", history, _settings(), TRACE
    )
    assert raw == "what about B2B?"
    assert condensed == "What does B2B activation look like?"
    assert fake_client.last_body is not None
    prompt = fake_client.last_body["messages"][1]["content"]
    assert "our activation dropped" in prompt
    assert "what about B2B?" in prompt
    assert fake_client.last_body["options"]["temperature"] == 0


async def test_history_is_truncated_to_max_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeAsyncClient("condensed query")
    monkeypatch.setattr(condense_module.httpx, "AsyncClient", fake_client)

    history = [_msg("user", f"turn {i}") for i in range(10)]
    await condense_module.condense("follow up", history, _settings(), TRACE, max_history_turns=2)
    assert fake_client.last_body is not None
    prompt = fake_client.last_body["messages"][1]["content"]
    assert "turn 8" in prompt
    assert "turn 9" in prompt
    assert "turn 0" not in prompt
