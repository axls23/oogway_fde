"""Unit tests for the relevance floor (AC3) and session boost, entirely in
isolation from any real model or DB — injected fake ScoredChunk lists only.
This is the test the api/CLAUDE.md non-negotiable-behaviors section points
at: "retrieval.py's relevance floor is a plain Python if guard... this is
what AC3 tests."
"""

from __future__ import annotations

from app.services.retrieval import (
    GUEST_NAME_BOOST,
    ScoredChunk,
    apply_floor,
    apply_guest_boost,
    apply_session_boost,
)


def _chunk(
    chunk_id: int, episode_id: int, score: float, guest: str | None = None
) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id,
        episode_id=episode_id,
        episode_title=f"Episode {episode_id}",
        guest=guest if guest is not None else f"Guest {episode_id}",
        youtube_url="https://youtube.com/watch?v=x",
        start_seconds=42,
        text="some transcript text",
        score=score,
    )


def test_floor_abstains_when_all_scores_below_floor() -> None:
    # This is the AC3 shape: 5 out-of-corpus-style questions, every
    # candidate scores below the floor -> the system must abstain, not
    # answer with weak context.
    chunks = [_chunk(1, 1, 0.10), _chunk(2, 2, 0.22), _chunk(3, 3, 0.05)]
    result = apply_floor(chunks, floor=0.45)
    assert result.abstained is True
    assert result.chunks == []


def test_floor_abstains_on_empty_candidate_list() -> None:
    result = apply_floor([], floor=0.45)
    assert result.abstained is True
    assert result.chunks == []


def test_floor_returns_top_n_when_max_score_clears_floor() -> None:
    chunks = [_chunk(i, i, score) for i, score in enumerate([0.9, 0.8, 0.7, 0.6, 0.5, 0.1], 1)]
    result = apply_floor(chunks, floor=0.45, return_n=4)
    assert result.abstained is False
    assert [c.chunk_id for c in result.chunks] == [1, 2, 3, 4]
    assert [c.score for c in result.chunks] == [0.9, 0.8, 0.7, 0.6]


def test_floor_boundary_is_strict_less_than() -> None:
    # A score exactly AT the floor clears it (the guard is `< floor`, not
    # `<= floor`) — pin this down explicitly since it's an off-by-one that
    # would silently change AC3's pass rate.
    chunks = [_chunk(1, 1, 0.45)]
    result = apply_floor(chunks, floor=0.45)
    assert result.abstained is False
    assert len(result.chunks) == 1


def test_session_boost_adds_flat_bonus_capped_at_one() -> None:
    chunks = [_chunk(1, 10, 0.98), _chunk(2, 20, 0.50)]
    boosted = apply_session_boost(chunks, boosted_episode_ids={10})
    assert boosted[0].score == 1.0  # 0.98 + 0.05 capped
    assert boosted[1].score == 0.50  # episode 20 was never cited, untouched


def test_session_boost_cannot_flip_a_strong_new_topic_below_a_stale_one() -> None:
    # Boost is +0.05 flat: a genuine topic change with a score more than
    # 0.05 ahead of a boosted stale-episode chunk still wins the floor/rank.
    stale = _chunk(1, 10, 0.50)
    fresh = _chunk(2, 20, 0.90)
    boosted = apply_session_boost([stale, fresh], boosted_episode_ids={10})
    result = apply_floor(boosted, floor=0.45, return_n=1)
    assert result.chunks[0].chunk_id == 2


def test_abstained_result_never_leaks_low_scoring_chunks() -> None:
    # Defense in depth: even if a caller ignores `abstained`, `chunks` must
    # be empty so nothing weak can accidentally be cited (invariant 1: no
    # citation exists that retrieval.py didn't hand back explicitly).
    chunks = [_chunk(1, 1, 0.44)]
    result = apply_floor(chunks, floor=0.45)
    assert result.chunks == []


def test_guest_boost_applies_on_full_name_match() -> None:
    chunks = [
        _chunk(1, 10, 0.50, guest="Shreyas Doshi"),
        _chunk(2, 20, 0.50, guest="Someone Else"),
    ]
    boosted = apply_guest_boost(chunks, "what did Shreyas Doshi say about onboarding?")
    assert boosted[0].score == round(0.50 + GUEST_NAME_BOOST, 10)
    assert boosted[1].score == 0.50  # no mention of this guest -> untouched


def test_guest_boost_applies_on_last_name_only_token_match() -> None:
    # "Doshi" alone (no first name) should still trigger the boost — users
    # plausibly refer to a guest by last name only.
    chunks = [_chunk(1, 10, 0.50, guest="Shreyas Doshi")]
    boosted = apply_guest_boost(chunks, "what did Doshi say about onboarding?")
    assert boosted[0].score == round(0.50 + GUEST_NAME_BOOST, 10)


def test_guest_boost_no_match_leaves_score_untouched() -> None:
    chunks = [_chunk(1, 10, 0.50, guest="Shreyas Doshi")]
    boosted = apply_guest_boost(chunks, "how should I think about pricing pages?")
    assert boosted[0].score == 0.50


def test_guest_boost_capped_at_one_when_combined_with_high_score() -> None:
    chunks = [_chunk(1, 10, 0.99, guest="Shreyas Doshi")]
    boosted = apply_guest_boost(chunks, "what did Shreyas Doshi say?")
    assert boosted[0].score == 1.0  # 0.99 + GUEST_NAME_BOOST capped


def test_guest_boost_avoids_false_positive_on_short_or_substring_fragment() -> None:
    # "Baker" is a common-enough last name that a naive substring check
    # (`"baker" in query`) would spuriously match "bakery", boosting an
    # unrelated chunk about baked goods. Whole-word token matching avoids
    # this: "bakery" tokenizes to "bakery", not "baker".
    chunks = [_chunk(1, 10, 0.50, guest="Ed Baker")]
    boosted = apply_guest_boost(chunks, "where's a good bakery near me?")
    assert boosted[0].score == 0.50

    # And a short fragment like "Ed" (below GUEST_NAME_MIN_TOKEN_LEN) is
    # never treated as a distinctive-enough token to boost on by itself,
    # even when it appears as its own word in the query.
    boosted_short = apply_guest_boost(chunks, "ed, what should I do next?")
    assert boosted_short[0].score == 0.50


def test_guest_boost_single_word_short_name_does_not_bypass_length_guard() -> None:
    # A guest whose full name is a single short word (e.g. "Al") must not
    # sneak past the length guard via the full-name substring branch --
    # otherwise any query containing "al" as a substring ("actually",
    # "practical") would spuriously boost this guest's chunks.
    chunks = [_chunk(1, 10, 0.50, guest="Al")]
    boosted = apply_guest_boost(chunks, "actually, I want to talk about pricing")
    assert boosted[0].score == 0.50
