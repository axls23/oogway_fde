"""INTEGRATION TEST — exercises the REAL Ollama instance at OLLAMA_BASE_URL
(default http://127.0.0.1:11434), not a mock. This is the one place in the
suite that does AC4's actual claim: a three-turn pronominal chain
("what about B2B?", "expand on that") must resolve to on-topic standalone
queries, which requires a real model doing real reasoning — a mocked HTTP
call would only prove the plumbing (see test_condense.py for that).

Skipped automatically if Ollama or the qwen2.5:7b-instruct model isn't
reachable, so `make test`/`pytest -q` never fails in an environment without
a live Ollama. Run explicitly with:
    pytest -q tests/test_condense_integration.py -m integration
"""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.db.models import Message
from app.services.condense import condense

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "qwen2.5:7b-instruct"


def _ollama_ready() -> bool:
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
        names = [m["name"] for m in resp.json().get("models", [])]
        return resp.status_code == 200 and any(MODEL in n for n in names)
    except httpx.HTTPError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ollama_ready(), reason=f"Ollama/{MODEL} not reachable at {OLLAMA_URL}"),
]


def _msg(role: str, content: str) -> Message:
    return Message(session_id=None, role=role, content=content, trace_id="x")  # type: ignore[arg-type]


async def test_three_turn_pronominal_chain_resolves_on_topic() -> None:
    settings = Settings(llm_provider="ollama", llm_model=MODEL, ollama_base_url=OLLAMA_URL)
    history: list[Message] = []

    # Turn 1
    raw1 = "our activation dropped after we added a second onboarding step, what do people say about this"
    _, condensed1 = await condense(raw1, history, settings, "trace-1")
    assert condensed1  # turn 1 is a no-op passthrough, always non-empty
    history.append(_msg("user", raw1))
    history.append(_msg("assistant", "Several guests discuss onboarding friction and step count."))

    # Turn 2 — pronominal follow-up
    raw2 = "what about B2B?"
    _, condensed2 = await condense(raw2, history, settings, "trace-2")
    lowered2 = condensed2.lower()
    assert "b2b" in lowered2
    assert lowered2.strip() != raw2.lower()  # must have actually rewritten, not passed through
    assert any(kw in lowered2 for kw in ("onboard", "activation", "step"))
    history.append(_msg("user", raw2))
    history.append(_msg("assistant", "B2B onboarding differs in buyer count and time-to-value."))

    # Turn 3 — a second pronominal follow-up referring further back
    raw3 = "expand on that"
    _, condensed3 = await condense(raw3, history, settings, "trace-3")
    lowered3 = condensed3.lower()
    assert lowered3.strip() != raw3.lower()
    assert any(kw in lowered3 for kw in ("b2b", "onboard", "activation"))
