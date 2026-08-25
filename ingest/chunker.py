"""Fixed-size chunking with speaker-turn-aware boundaries.

architecture.md §6 / §7.3: ~800 tokens per chunk, 15% overlap, prefer
splitting on speaker-turn boundaries over blind character/token windows.

Token counting: we approximate tokens as `round(word_count * WORDS_TO_TOKENS)`
rather than pulling in a real tokenizer (tiktoken or the qwen2.5 tokenizer).
Two reasons: (1) neither tokenizer matches the embedding model actually used
here (`nomic-embed-text`, a llama.cpp/BERT-family model) or the generation
model (`qwen2.5:7b-instruct`) closely enough to be worth the precision: this
is a chunk-sizing heuristic, not a token-billing calculation; (2) tiktoken's
encoders are not vendored -- they fetch BPE rank files over the network on
first use, which would silently give `ingest.py` a network dependency the
rest of the system deliberately avoids (architecture.md §1: "No network
dependency at boot"). A words-to-tokens ratio of 1.3 (i.e. ~0.77 words per
token) is the commonly cited average for English prose and is deterministic,
dependency-free, and good enough to hit "~800 tokens" within a reasonable
band. `chunks.token_count` in the DB is this same estimate -- documented here
so nobody mistakes it for an exact tokenizer count later.
"""

from __future__ import annotations

from dataclasses import dataclass

from transcript import Turn

WORDS_TO_TOKENS = 1.3
TARGET_TOKENS = 800
OVERLAP_RATIO = 0.15

TARGET_WORDS = round(TARGET_TOKENS / WORDS_TO_TOKENS)
OVERLAP_WORDS = round(TARGET_WORDS * OVERLAP_RATIO)


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    token_count: int
    start_seconds: int | None


def _format_turn(turn: Turn) -> str:
    """Render one turn as clean prose for embedding/storage: speaker name
    kept (useful signal for retrieval and for a human reading the verbatim
    snippet in flow F2), the raw "(HH:MM:SS):" timestamp marker dropped --
    that's the "speaker-label noise" architecture.md §6 says to strip, now
    that parse_turns() has already extracted it into `start_seconds`."""
    if turn.speaker:
        return f"{turn.speaker}: {turn.text}"
    return turn.text


def _word_count(text: str) -> int:
    return len(text.split())


def _estimate_tokens(word_count: int) -> int:
    return max(1, round(word_count * WORDS_TO_TOKENS))


def _split_oversized_turn(turn: Turn) -> list[Turn]:
    """A single turn whose word count alone exceeds TARGET_WORDS (a long
    monologue) can't be kept whole without blowing the chunk size budget.
    Split it at word boundaries into TARGET_WORDS-sized pieces -- the one
    case where we do split mid-turn, because the alternative (one enormous
    chunk) is worse for retrieval precision. Each piece keeps the parent
    turn's start_seconds; we have no finer-grained timestamp inside it."""
    words = turn.text.split()
    if len(words) <= TARGET_WORDS:
        return [turn]
    pieces: list[Turn] = []
    for start in range(0, len(words), TARGET_WORDS):
        piece_words = words[start : start + TARGET_WORDS]
        pieces.append(Turn(speaker=turn.speaker, start_seconds=turn.start_seconds, text=" ".join(piece_words)))
    return pieces


def chunk_turns(turns: list[Turn]) -> list[Chunk]:
    """Pack speaker turns into ~TARGET_TOKENS chunks with ~OVERLAP_RATIO
    overlap, preferring to keep whole turns together and only splitting a
    turn internally when it alone exceeds the target size.

    Boundary strategy: greedily accumulate whole turns until the running
    word count reaches TARGET_WORDS, close the chunk, then step the start
    index back over as many trailing turns as needed to cover
    OVERLAP_WORDS -- so the next chunk repeats the tail of this one instead
    of starting from a hard cut. Progress is always guaranteed (the start
    index strictly increases each iteration).
    """
    if not turns:
        return []

    # Expand any oversized single turn into several turn-like pieces first,
    # so the packing loop below only ever deals with turns <= TARGET_WORDS.
    expanded: list[Turn] = []
    for t in turns:
        expanded.extend(_split_oversized_turn(t))

    word_counts = [_word_count(t.text) for t in expanded]

    chunks: list[Chunk] = []
    i = 0
    n = len(expanded)
    ordinal = 0

    while i < n:
        j = i
        total = 0
        # Accumulate whole turns until we hit (or would exceed) the target.
        while j < n:
            total += word_counts[j]
            j += 1
            if total >= TARGET_WORDS:
                break
        # j is exclusive end index; chunk covers turns[i:j]
        chunk_turns_slice = expanded[i:j]
        text = "\n\n".join(_format_turn(t) for t in chunk_turns_slice)
        # Recomputed from the formatted `text`, not summed from `word_counts`
        # (which are pre-formatting, i.e. exclude each turn's "Speaker: "
        # prefix) -- token_count should describe what's actually stored in
        # chunks.text, and packing decisions above only need the raw sum as
        # a size *estimate* for the accumulate/break loop, not as the
        # persisted count.
        word_count = _word_count(text)
        start_seconds = next(
            (t.start_seconds for t in chunk_turns_slice if t.start_seconds is not None),
            None,
        )
        chunks.append(
            Chunk(
                ordinal=ordinal,
                text=text,
                token_count=_estimate_tokens(word_count),
                start_seconds=start_seconds,
            )
        )
        ordinal += 1

        if j >= n:
            break

        # Walk back from j to find how many trailing turns cover
        # OVERLAP_WORDS; the next chunk starts there instead of at j.
        back = j - 1
        overlap_total = word_counts[back]
        while back > i and overlap_total < OVERLAP_WORDS:
            back -= 1
            overlap_total += word_counts[back]

        next_i = back if back > i else j  # guarantee forward progress
        i = next_i

    return chunks
