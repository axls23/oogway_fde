"""Retrieval pipeline: embed -> top-k -> session boost -> guest-name boost ->
relevance floor -> top 4.

architecture.md §7 / api/CLAUDE.md: step 5, the relevance floor, MUST be a
plain Python `if` guard evaluated before any model call — never a prompt
instruction. That's the mechanism behind AC3 (5/5 out-of-corpus questions
must abstain) and it lives in `apply_floor` below, called unconditionally
before `retrieve()` returns.

This module has no dependency on the agent service or any LLM generation
call, so it is unit-testable in isolation (api/CLAUDE.md, architecture.md
§2) by injecting a fake embed function and fake DB rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Chunk, Citation, Episode, Message
from app.errors import ApiError, provider_unreachable
from app.obs.logging import Stopwatch, log_event

# Guest-name boost isn't (yet) env-configurable like SESSION_BOOST/
# TOP_K_DEFAULT/RETURN_N (Settings.session_boost/top_k_default/return_n) —
# no task has asked for that, and these two are cheap to change here if
# that ever comes up.
GUEST_NAME_BOOST = 0.03
GUEST_NAME_MIN_TOKEN_LEN = 4


@dataclass
class ScoredChunk:
    chunk_id: int
    episode_id: int
    episode_title: str
    guest: str
    youtube_url: str | None
    start_seconds: int | None
    text: str
    score: float


@dataclass
class RetrieveResult:
    abstained: bool
    floor: float
    chunks: list[ScoredChunk]


async def embed_query(query: str, settings: Settings, trace_id: str) -> list[float]:
    """Call Ollama's embeddings endpoint. Raises ApiError(503) if unreachable.

    No silent failover, no fallback embedding (root CLAUDE.md forbidden
    pattern: silent fallback paths) — a failed embed call is a failed turn.
    """
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"
    try:
        async with httpx.AsyncClient(timeout=settings.model_timeout_s) as client:
            resp = await client.post(
                url, json={"model": settings.embed_model, "prompt": query}
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log_event(
            "embed_query_failed", trace_id, level=40, error=str(exc), url=url
        )
        raise provider_unreachable("ollama", trace_id, detail=str(exc)) from exc

    embedding = data.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise ApiError(
            502,
            "OLLAMA_BAD_RESPONSE",
            "Ollama returned an embedding response with no vector",
            trace_id=trace_id,
        )
    return [float(x) for x in embedding]


async def _previously_cited_episode_ids(
    db: AsyncSession, session_id: uuid.UUID
) -> set[int]:
    stmt = (
        select(Chunk.episode_id)
        .join(Citation, Citation.chunk_id == Chunk.id)
        .join(Message, Message.id == Citation.message_id)
        .where(Message.session_id == session_id)
        .distinct()
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}


async def _top_k_by_cosine(
    db: AsyncSession, embedding: list[float], k: int
) -> list[ScoredChunk]:
    distance = Chunk.embedding.cosine_distance(embedding).label("distance")
    stmt = (
        select(
            Chunk.id,
            Chunk.episode_id,
            Chunk.text,
            Chunk.start_seconds,
            Episode.title,
            Episode.guest,
            Episode.youtube_url,
            distance,
        )
        .join(Episode, Episode.id == Chunk.episode_id)
        .order_by(distance)
        .limit(k)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        ScoredChunk(
            chunk_id=r.id,
            episode_id=r.episode_id,
            episode_title=r.title,
            guest=r.guest,
            youtube_url=r.youtube_url,
            start_seconds=r.start_seconds,
            text=r.text,
            score=1.0 - float(r.distance),
        )
        for r in rows
    ]


def apply_session_boost(
    chunks: list[ScoredChunk],
    boosted_episode_ids: set[int],
    boost: float = 0.05,
) -> list[ScoredChunk]:
    """+boost to chunks from episodes already cited this session.

    Capped at score 1.0 (cosine similarity's ceiling) so the boost can
    never invert a strong new-topic match below a weak previously-cited
    one by more than `boost` — a genuine topic change can still out-rank a
    boosted stale episode as long as its unboosted score beats the boosted
    one by more than `boost`. `boost` defaults to the historical hardcoded
    value (0.05); callers going through `retrieve()` get it from
    `Settings.session_boost` (env var `SESSION_BOOST`) instead.
    """
    for c in chunks:
        if c.episode_id in boosted_episode_ids:
            c.score = min(1.0, c.score + boost)
    return chunks


def _normalize_query_tokens(query: str) -> set[str]:
    """Lowercase, whitespace-split query into a set of punctuation-stripped
    word tokens, for exact (not substring) token matching.

    Plain string ops only (root/api CLAUDE.md: no new dependency, no regex
    library) — `.lower()`, `.split()`, `.strip()` on a fixed punctuation set.
    """
    tokens: set[str] = set()
    for word in query.lower().split():
        stripped = word.strip(".,!?;:'\"()[]{}")
        if stripped:
            tokens.add(stripped)
    return tokens


def _guest_matches_query(guest: str, query: str) -> bool:
    """True if `guest`'s full name, or one distinctive token of it, is
    referenced in `query`.

    Two match modes:
    - Full (multi-word) name as a substring of the (lowercased) query —
      handles "what did Shreyas Doshi say about onboarding?" directly.
      Only used when the guest's name has more than one word: a two-plus
      word phrase is distinctive enough to match as a raw substring
      without a length guard.
    - A single name token (e.g. just the last name, "Doshi") matched as a
      *whole word* against the query's own tokens — handles "what did
      Doshi say about onboarding?" without requiring the full name. This
      is also the only path used for a guest whose full name is itself a
      single word, so a short one-word name doesn't skip the length guard
      by going through the substring branch instead.

    Whole-word token matching (not substring-in-query) is deliberate: a
    substring check would let a guest named e.g. "Ed Baker" spuriously
    match any query mentioning "bakery" ("baker" is a substring of
    "bakery"), boosting an unrelated chunk. Tokens shorter than
    GUEST_NAME_MIN_TOKEN_LEN are skipped entirely for the same reason in
    the other direction: a short, common fragment (e.g. "Al", "Ed", "Jo")
    is too likely to collide with an ordinary word or an unrelated guest's
    initials to be treated as a distinctive signal.
    """
    guest_lower = guest.lower().strip()
    if not guest_lower:
        return False
    name_tokens = guest_lower.split()
    if len(name_tokens) > 1 and guest_lower in query.lower():
        return True
    query_tokens = _normalize_query_tokens(query)
    for name_token in name_tokens:
        if len(name_token) >= GUEST_NAME_MIN_TOKEN_LEN and name_token in query_tokens:
            return True
    return False


def apply_guest_boost(chunks: list[ScoredChunk], query: str) -> list[ScoredChunk]:
    """+GUEST_NAME_BOOST to chunks whose episode guest is named in `query`.

    Mirrors apply_session_boost's shape exactly: a flat additive bump,
    capped at score 1.0, applied per-chunk based on metadata already
    joined onto the candidate (episode.guest here, episode_id-in-session
    there) — never a separate scoring path the floor doesn't see.

    GUEST_NAME_BOOST (0.03) is deliberately smaller than the default
    session boost (0.05): "this guest was already cited earlier in this
    session" is a session-scoped fact with no ambiguity, whereas "the
    guest's name (or a token of it) appears in the query text" is a
    noisier, string-match signal — the query could mention a guest's name
    in passing, in a comparison ("more direct than Shreyas Doshi's usual
    take"), or match a distinctive-but-coincidental token. A smaller cap
    keeps this boost unable to outweigh a materially stronger embedding
    match on its own, while still being enough to break near-ties in favor
    of the explicitly-named guest's episode.
    """
    for c in chunks:
        if _guest_matches_query(c.guest, query):
            c.score = min(1.0, c.score + GUEST_NAME_BOOST)
    return chunks


def apply_floor(
    chunks: list[ScoredChunk], floor: float, return_n: int = 4
) -> RetrieveResult:
    """The relevance floor. Plain Python `if`, not a prompt instruction.

    This is the entire mechanism behind AC3: if nothing clears the floor,
    the request short-circuits with abstained=True and an EMPTY chunk list,
    before any model ever sees a shred of context.
    """
    if not chunks or max(c.score for c in chunks) < floor:
        return RetrieveResult(abstained=True, floor=floor, chunks=[])
    ranked = sorted(chunks, key=lambda c: c.score, reverse=True)[:return_n]
    return RetrieveResult(abstained=False, floor=floor, chunks=ranked)


async def retrieve(
    db: AsyncSession,
    settings: Settings,
    query: str,
    session_id: uuid.UUID,
    trace_id: str,
    k: int | None = None,
    return_n: int | None = None,
) -> RetrieveResult:
    """Full pipeline: embed condensed query -> top-k -> boost -> floor -> top N.

    Callers are expected to have already condensed the raw user message
    into `query` (see services/condense.py) — this function does not
    condense, it only embeds and searches. `k` and `return_n` default to
    `Settings.top_k_default` / `Settings.return_n` (env vars TOP_K_DEFAULT /
    RETURN_N, both 8/4 out of the box, architecture.md §7) when the caller
    doesn't pass an explicit value — routers/internal.py's /internal/retrieve
    always passes `k` explicitly (from `RetrieveRequest.k`, itself defaulted
    to 8 by the API contract in contracts/openapi.yaml), so this default only
    matters for the direct-call path in services/turn.py; ship30.py passes a
    larger `return_n` for its wider retrieval set (PRD F3 step 2).
    """
    if k is None:
        k = settings.top_k_default
    if return_n is None:
        return_n = settings.return_n
    with Stopwatch() as sw_embed:
        embedding = await embed_query(query, settings, trace_id)
    with Stopwatch() as sw_search:
        candidates = await _top_k_by_cosine(db, embedding, max(k, return_n))
        boosted_ids = await _previously_cited_episode_ids(db, session_id)
        candidates = apply_session_boost(candidates, boosted_ids, settings.session_boost)
        candidates = apply_guest_boost(candidates, query)
    result = apply_floor(candidates, settings.retrieval_floor, return_n=return_n)
    log_event(
        "retrieve",
        trace_id,
        session_id=str(session_id),
        duration_ms=sw_embed.ms + sw_search.ms,
        query=query,
        k=k,
        candidate_count=len(candidates),
        abstained=result.abstained,
        floor=result.floor,
        top_scores=[round(c.score, 4) for c in candidates[:k]],
        returned_chunk_ids=[c.chunk_id for c in result.chunks],
    )
    return result
