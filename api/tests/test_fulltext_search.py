"""Integration tests for the full-text side of hybrid retrieval
(chunks.text_search, GIN-indexed, populated by contracts/schema.sql's
generated column) -- needs a real Postgres connection, same as
test_ivfflat_probes.py style, since `to_tsvector`/`ts_rank_cd`/`@@` have no
meaningful fake.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval import _top_k_by_fulltext


async def _seed_episode_and_chunks(db: AsyncSession) -> None:
    await db.execute(
        text(
            "INSERT INTO episodes (id, title, guest, youtube_url, source_path, content_hash) "
            "VALUES (1, 'Ep', 'Guest', NULL, '/tmp/ep1.md', 'deadbeef')"
        )
    )
    rows = [
        (1, 0, "we talked a lot about product market fit and early-stage growth strategy"),
        (2, 1, "pricing pages and subscription billing came up several times"),
        (3, 2, "the weather today is sunny with a light breeze"),
    ]
    for chunk_id, ordinal, chunk_text in rows:
        await db.execute(
            text(
                "INSERT INTO chunks (id, episode_id, ordinal, text, token_count, "
                "start_seconds, embedding) "
                "VALUES (:id, 1, :ordinal, :text, 10, 0, :embedding)"
            ),
            {
                "id": chunk_id,
                "ordinal": ordinal,
                "text": chunk_text,
                "embedding": str([0.1] * 768),
            },
        )
    await db.commit()


async def test_fulltext_search_ranks_matching_chunk_first(db_session: AsyncSession) -> None:
    await _seed_episode_and_chunks(db_session)

    ids = await _top_k_by_fulltext(db_session, "product market fit", k=5)

    assert ids[0] == 1  # the only chunk mentioning product/market/fit


def test_fulltext_search_is_a_coroutine_function() -> None:
    # Cheap smoke check that the function stayed async (a sync/async
    # mismatch here would silently break retrieve()'s asyncio.gather).
    import inspect

    assert inspect.iscoroutinefunction(_top_k_by_fulltext)


async def test_fulltext_search_returns_empty_list_for_no_match(db_session: AsyncSession) -> None:
    await _seed_episode_and_chunks(db_session)

    ids = await _top_k_by_fulltext(db_session, "nuclear fusion containment vessel", k=5)

    assert ids == []


async def test_fulltext_search_handles_query_with_no_lexical_terms(
    db_session: AsyncSession,
) -> None:
    # All-stopword / punctuation-only query: websearch_to_tsquery can
    # legitimately produce an empty tsquery. Must not raise.
    await _seed_episode_and_chunks(db_session)

    ids = await _top_k_by_fulltext(db_session, "the a of", k=5)

    assert ids == []
