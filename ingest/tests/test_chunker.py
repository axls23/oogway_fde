"""Tests for chunker.py: token-count estimation and turn-boundary-aware
overlap behavior."""

from __future__ import annotations

from chunker import (
    OVERLAP_WORDS,
    TARGET_TOKENS,
    TARGET_WORDS,
    WORDS_TO_TOKENS,
    chunk_turns,
)
from transcript import Turn


def _turn(speaker: str, seconds: int, n_words: int, turn_id: int = 0) -> Turn:
    # Words are tagged with turn_id so distinct turns never share literal
    # tokens -- needed so overlap tests actually prove word-sharing comes
    # from the chunker's overlap window, not from coincidentally identical
    # placeholder text.
    text = " ".join(f"t{turn_id}w{i}" for i in range(n_words))
    return Turn(speaker=speaker, start_seconds=seconds, text=text)


def test_chunk_turns_empty_input():
    assert chunk_turns([]) == []


def test_chunk_turns_single_small_turn_is_one_chunk():
    turns = [_turn("Guest", 0, 20)]
    chunks = chunk_turns(turns)
    assert len(chunks) == 1
    assert chunks[0].ordinal == 0
    assert chunks[0].start_seconds == 0
    assert "Guest:" in chunks[0].text


def test_chunk_turns_ordinals_are_sequential_from_zero():
    # Enough turns to force multiple chunks.
    turns = [_turn("Guest", i * 30, 200, turn_id=i) for i in range(10)]
    chunks = chunk_turns(turns)
    assert len(chunks) > 1
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_chunk_turns_respects_target_word_budget_per_chunk():
    # Many small turns; each chunk should stop accumulating once it reaches
    # TARGET_WORDS (it may exceed slightly since whole turns aren't split).
    turns = [_turn("Guest", i * 10, 50, turn_id=i) for i in range(30)]
    chunks = chunk_turns(turns)
    for c in chunks[:-1]:  # last chunk may be short (leftover)
        word_count = len(c.text.split())
        # each turn contributes "Guest:" (1 extra token-ish word) + 50 words
        assert word_count >= TARGET_WORDS


def test_chunk_turns_token_count_matches_word_based_estimate():
    turns = [_turn("Guest", 0, 100)]
    chunks = chunk_turns(turns)
    word_count = len(chunks[0].text.split())
    assert chunks[0].token_count == round(word_count * WORDS_TO_TOKENS)


def test_chunk_turns_does_not_split_a_turn_that_fits():
    # A turn just under TARGET_WORDS should never be split even though a
    # second turn pushes the running total over the target.
    turns = [_turn("A", 0, TARGET_WORDS - 10, turn_id=1), _turn("B", 5, 5, turn_id=2)]
    chunks = chunk_turns(turns)
    # Both turns fit in one chunk (packing stops once total >= TARGET_WORDS,
    # and the first turn alone is already close); assert speaker labels for
    # both appear intact (not truncated mid-turn).
    assert "A:" in chunks[0].text
    full_text = "\n\n".join(c.text for c in chunks)
    assert full_text.count("A:") == 1
    assert full_text.count("B:") == 1


def test_chunk_turns_splits_oversized_single_turn():
    # A single turn far larger than TARGET_WORDS must be split into pieces,
    # each carrying the parent turn's start_seconds (no finer-grained
    # timestamp is available inside one turn).
    turns = [_turn("Monologue", 42, TARGET_WORDS * 3)]
    chunks = chunk_turns(turns)
    assert len(chunks) >= 3
    for c in chunks:
        assert c.start_seconds == 42


def test_chunk_turns_produces_overlap_between_consecutive_chunks():
    # Many medium turns so overlap has room to operate (chunk spans several
    # turns, so the overlap window can land strictly inside the chunk
    # without being forced to the chunk boundary).
    turns = [_turn("Guest", i * 5, 60, turn_id=i) for i in range(20)]
    chunks = chunk_turns(turns)
    assert len(chunks) >= 2

    # Overlap check: chunk[1] should share some trailing words of chunk[0].
    words0 = chunks[0].text.split()
    words1 = chunks[1].text.split()
    tail0 = set(words0[-OVERLAP_WORDS:]) if len(words0) >= OVERLAP_WORDS else set(words0)
    head1 = set(words1[: len(tail0)])
    assert tail0 & head1, "expected some shared words between consecutive chunks (overlap)"


def test_chunk_turns_start_seconds_is_first_turns_timestamp():
    turns = [
        Turn(speaker="A", start_seconds=None, text="leading text with no timestamp " * 5),
        Turn(speaker="B", start_seconds=100, text="second turn " * 5),
    ]
    chunks = chunk_turns(turns)
    # start_seconds should come from the first turn in the chunk that HAS a
    # timestamp, per architecture.md: "nearest preceding speaker-turn
    # timestamp".
    assert chunks[0].start_seconds == 100


def test_target_tokens_constant_is_800_per_spec():
    assert TARGET_TOKENS == 800
