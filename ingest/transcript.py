"""Parsing for corpus transcript.md files: YAML frontmatter + speaker-turn body.

Governed by ../contracts/schema.sql and ingest/CLAUDE.md. See that file for the
confirmed corpus format (verified 2026-08-24): YAML frontmatter delimited by
`---` lines, then `# {title}\n\n## Transcript\n\n`, then a body of repeating
`Speaker Name (HH:MM:SS):\n{text}\n\n` turns. A minority of episodes use
`(MM:SS)` instead of `(HH:MM:SS)`, and some turns continue a paragraph under a
bare `(HH:MM:SS):` marker with no speaker name repeated -- both are handled
here.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

import yaml

logger = logging.getLogger("ingest.transcript")

# Frontmatter is the block between the first line ("---") and the next line
# that is exactly "---". Non-greedy so a value containing "---" mid-string
# (not as its own line) doesn't confuse the match.
_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)

# A speaker-turn header line, e.g.:
#   "Ada Chen Rekhi (00:00:00):"      -- named turn, HH:MM:SS
#   "Sahil Bloom (00:14):"            -- named turn, MM:SS (short episodes)
#   "(00:01:21):"                     -- continuation of the previous speaker
# Speaker names may contain '+' or '&' for co-guests (e.g. "Jake Knapp + John
# Zeratsky"), so we don't restrict punctuation beyond excluding '(' and '\n'.
_TURN_HEADER_RE = re.compile(
    # NOTE: the gap before "(" is [ \t]* (same-line only), not \s* -- \s*
    # would also match a blank-line separator, which let a bare continuation
    # marker like "(00:01:21):" get mis-parsed with the *entire preceding
    # paragraph* captured as its "speaker" (that paragraph ends a line,
    # satisfying ^, then \s* would swallow the blank line up to the next
    # "("). Caught by test_parse_turns_dominant_format_extracts_speakers_and_timestamps.
    r"^(?:(?P<speaker>[A-Za-z][^\n(]*?)[ \t]*)?\((?P<ts>\d{1,2}(?::\d{2}){1,2})\):[ \t]*$",
    re.MULTILINE,
)

# Fallback A -- inline bracket timestamp, whole turn on one line:
#   "[00:00:28] Lenny: Ryan Hoover is the founder of Product Hunt..."
# Observed on exactly one episode in the corpus (episodes/ryan-hoover) as of
# the 2026-08-24 spot-check; kept as a narrow, line-scoped fallback so it
# can never fire against the dominant header-block format above.
_INLINE_BRACKET_RE = re.compile(
    r"^\[(?P<ts>\d{1,2}(?::\d{2}){1,2})\]\s*(?P<speaker>[^:\n]{1,80}):\s*(?P<text>.*)$",
    re.MULTILINE,
)

# Fallback B -- bare "Speaker:" header with no timestamp at all:
#   "Adriel Frederick:\n{text}\n\n"
# Observed on exactly one episode (episodes/adriel-frederick). Turns parsed
# this way always get start_seconds=None -- there is no timestamp to
# recover. Speaker names are capped at 80 chars to keep this from matching
# an arbitrary "Label:" line inside ordinary prose.
_NAME_ONLY_HEADER_RE = re.compile(
    r"^(?P<speaker>[A-Za-z][^\n:]{0,79}):[ \t]*$",
    re.MULTILINE,
)


class MalformedTranscriptError(ValueError):
    """Raised when a transcript.md cannot be turned into a valid episode row."""


@dataclass(frozen=True)
class Frontmatter:
    guest: str
    title: str
    youtube_url: str | None
    video_id: str | None
    publish_date: str | None  # ISO date string ("YYYY-MM-DD") or None
    duration_seconds: int | None


@dataclass(frozen=True)
class Turn:
    """One speaker-turn segment: a contiguous run of text following one
    timestamp marker. Continuation markers (no repeated speaker name) carry
    the most recently seen speaker forward."""

    speaker: str | None
    start_seconds: int | None
    text: str


def content_hash(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def _parse_timestamp(ts: str) -> int:
    """'MM:SS' or 'HH:MM:SS' -> integer seconds."""
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_duration(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_frontmatter(raw: str) -> Frontmatter:
    """Parse the YAML frontmatter block. Raises MalformedTranscriptError on
    any failure: missing delimiters, unparseable YAML, or missing a required
    field (`guest`, `title` -- both NOT NULL in contracts/schema.sql)."""
    match = _FRONTMATTER_RE.match(raw)
    if match is None:
        raise MalformedTranscriptError("missing or unterminated YAML frontmatter block")

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise MalformedTranscriptError(f"unparseable YAML frontmatter: {exc}") from exc

    if not isinstance(data, dict):
        raise MalformedTranscriptError("frontmatter did not parse to a mapping")

    guest = _clean_str(data.get("guest"))
    title = _clean_str(data.get("title"))
    if guest is None:
        raise MalformedTranscriptError("missing required frontmatter field: guest")
    if title is None:
        raise MalformedTranscriptError("missing required frontmatter field: title")

    return Frontmatter(
        guest=guest,
        title=title,
        youtube_url=_clean_str(data.get("youtube_url")),
        video_id=_clean_str(data.get("video_id")),
        publish_date=_clean_str(data.get("publish_date")),
        duration_seconds=_clean_duration(data.get("duration_seconds")),
    )


def split_frontmatter_and_body(raw: str) -> str:
    """Return the content after the frontmatter block and the `## Transcript`
    heading, if present. Falls back to everything after the frontmatter block
    if the heading isn't found (defensive; not observed in the corpus)."""
    match = _FRONTMATTER_RE.match(raw)
    if match is None:
        raise MalformedTranscriptError("missing or unterminated YAML frontmatter block")
    rest = raw[match.end():]
    heading_match = re.search(r"^##\s*Transcript\s*$", rest, re.MULTILINE)
    if heading_match is not None:
        return rest[heading_match.end():]
    return rest


def _parse_turns_header_format(body: str) -> list[Turn]:
    """Dominant corpus format: a "Speaker Name (HH:MM:SS):" (or bare
    "(HH:MM:SS):" continuation) header line followed by the turn's text on
    subsequent lines, up to the next header."""
    matches = list(_TURN_HEADER_RE.finditer(body))
    if not matches:
        return []

    turns: list[Turn] = []
    last_speaker: str | None = None

    # Text before the first marker, if any, becomes a speaker-less,
    # timestamp-less leading turn (not observed in the corpus, but the body
    # is otherwise not required to start exactly on a marker).
    first_start = matches[0].start()
    if body[:first_start].strip():
        turns.append(Turn(speaker=None, start_seconds=None, text=body[:first_start].strip()))

    for i, m in enumerate(matches):
        speaker = m.group("speaker")
        if speaker:
            speaker = speaker.strip()
            last_speaker = speaker
        else:
            speaker = last_speaker

        start_seconds = _parse_timestamp(m.group("ts"))
        text_start = m.end()
        text_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[text_start:text_end].strip()
        if text:
            turns.append(Turn(speaker=speaker, start_seconds=start_seconds, text=text))

    return turns


def _parse_turns_inline_bracket_format(body: str) -> list[Turn]:
    """Fallback A: "[HH:MM:SS] Speaker: text", one whole turn per line."""
    turns: list[Turn] = []
    for m in _INLINE_BRACKET_RE.finditer(body):
        text = m.group("text").strip()
        if text:
            turns.append(
                Turn(
                    speaker=m.group("speaker").strip(),
                    start_seconds=_parse_timestamp(m.group("ts")),
                    text=text,
                )
            )
    return turns


def _parse_turns_name_only_format(body: str) -> list[Turn]:
    """Fallback B: "Speaker:" header with no timestamp anywhere in the
    episode. start_seconds is always None for turns parsed this way."""
    matches = list(_NAME_ONLY_HEADER_RE.finditer(body))
    if not matches:
        return []

    turns: list[Turn] = []
    for i, m in enumerate(matches):
        speaker = m.group("speaker").strip()
        text_start = m.end()
        text_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[text_start:text_end].strip()
        if text:
            turns.append(Turn(speaker=speaker, start_seconds=None, text=text))
    return turns


def parse_turns(body: str) -> list[Turn]:
    """Split a transcript body into speaker-turn segments. Tries the
    dominant header format first, then two narrower fallbacks observed on a
    small minority of episodes during the 2026-08-24 corpus spot-check
    (inline "[HH:MM:SS] Speaker: text", and a no-timestamp "Speaker:"
    header). Empty/whitespace-only bodies, or bodies where none of the
    three strategies find a single turn, raise MalformedTranscriptError --
    the caller counts these as skipped."""
    if not body.strip():
        raise MalformedTranscriptError("transcript body is empty")

    turns = _parse_turns_header_format(body)
    if not turns:
        turns = _parse_turns_inline_bracket_format(body)
        if turns:
            logger.info("used inline-bracket fallback format (%d turns)", len(turns))
    if not turns:
        turns = _parse_turns_name_only_format(body)
        if turns:
            logger.info("used no-timestamp fallback format (%d turns)", len(turns))

    if not turns:
        raise MalformedTranscriptError("no speaker-turn markers found in body (tried 3 formats)")

    return turns
