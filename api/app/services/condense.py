"""Query condensation: last N turns + new message -> one standalone query.

architecture.md §7: "The single highest-value component in the system."
F1 follow-ups are pronominal ("what about B2B?", "expand on that") and
embedding those directly returns noise. This module makes one low-
temperature model call and returns exactly one line; both the raw and
condensed forms are meant to be persisted onto the `messages` row by the
caller (routers/sessions.py), per architecture.md §4's design note on
`messages.rewritten_query`.

This is a direct call to the configured provider (Ollama /api/chat, or
Anthropic's Messages API), not routed through the `agent` service — the
agent/Pi sidecar owns tool-using turn generation; condensation is a small,
single-purpose, non-tool completion that retrieval needs before the agent
is ever invoked, so it lives here in the same module as the rest of the
retrieval pipeline it feeds (architecture.md §2: "Retrieval lives in api").
"""

from __future__ import annotations

import httpx

from app.config import Settings
from app.db.models import Message
from app.errors import ApiError, provider_unreachable
from app.obs.logging import log_event
from app.services.provider import assert_provider_ready

SYSTEM_PROMPT = (
    "You rewrite a follow-up chat message into ONE standalone search query "
    "that captures what the user is asking, resolving pronouns and implicit "
    "references using the conversation history. Output ONLY the rewritten "
    "query on a single line, no preamble, no quotes, no explanation."
)


def _history_to_turns(history: list[Message], max_turns: int) -> list[Message]:
    return history[-max_turns:] if max_turns > 0 else []


def _build_prompt(history: list[Message], new_message: str) -> str:
    lines = []
    for m in history:
        speaker = "User" if m.role == "user" else "Assistant"
        lines.append(f"{speaker}: {m.content}")
    lines.append(f"User: {new_message}")
    lines.append("Standalone query:")
    return "\n".join(lines)


async def _condense_ollama(prompt: str, settings: Settings, trace_id: str) -> str:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.model_timeout_s) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log_event("condense_failed", trace_id, level=40, error=str(exc), url=url)
        raise provider_unreachable("ollama", trace_id, detail=str(exc)) from exc
    content = data.get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise ApiError(
            502, "OLLAMA_BAD_RESPONSE", "Ollama returned an empty condensation", trace_id=trace_id
        )
    return content


async def _condense_anthropic(prompt: str, settings: Settings, trace_id: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": settings.anthropic_api_key or "",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": settings.llm_model,
        "max_tokens": 128,
        "temperature": 0,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        async with httpx.AsyncClient(timeout=settings.model_timeout_s) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log_event("condense_failed", trace_id, level=40, error=str(exc), url=url)
        raise provider_unreachable("anthropic", trace_id, detail=str(exc)) from exc
    blocks = data.get("content", [])
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if not text.strip():
        raise ApiError(
            502,
            "ANTHROPIC_BAD_RESPONSE",
            "Anthropic returned an empty condensation",
            trace_id=trace_id,
        )
    return text


async def condense(
    raw_message: str,
    history: list[Message],
    settings: Settings,
    trace_id: str,
    max_history_turns: int = 6,
) -> tuple[str, str]:
    """Returns (raw_message, condensed_query).

    Turn 1 (no history) has nothing to condense — the raw message IS
    already a standalone query, so this short-circuits without a model
    call (PRD §6 F1 edge case). Every later turn goes through the model.
    """
    turns = _history_to_turns(history, max_history_turns)
    if not turns:
        log_event("condense", trace_id, skipped=True, reason="no_history")
        return raw_message, raw_message.strip()

    assert_provider_ready(settings, trace_id)
    prompt = _build_prompt(turns, raw_message)

    if settings.llm_provider == "anthropic":
        condensed = await _condense_anthropic(prompt, settings, trace_id)
    else:
        condensed = await _condense_ollama(prompt, settings, trace_id)

    condensed = condensed.strip().splitlines()[0].strip().strip('"')
    log_event(
        "condense",
        trace_id,
        skipped=False,
        raw=raw_message,
        condensed=condensed,
        history_turns=len(turns),
    )
    return raw_message, condensed
