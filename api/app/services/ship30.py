"""Ship 30 essay pipeline: outline -> per-section calls -> deterministic
assembly -> structural validation -> bounded repair (PRD F3, AC7).

Structure is guaranteed by this Python code, not by the model (PRD §7.8 /
architecture.md §8.4): the model only ever returns an outline (JSON) or a
section's prose (plain text); this module assembles the document and
enforces word count, heading count, citation coverage and non-empty
sections, then repairs at most one offending section.

# Reconciled against the real agent/src/server.ts (see agent_client.py):
# the wire protocol has no context_chunks/system_prompt/response_format
# fields — the agent is stateless per call and only ever sees
# {session_id, trace_id, messages}. Two consequences for this module:
#
# 1. There's no field to hand the model a candidate chunk set up front, and
#    no per-phase citation-collection mechanism on api's side (unlike the
#    primary F1 turn, where services/turn.py reads the agent's `citation`
#    wire events). So the chunk_ids an outline/section call cites have to
#    come from chunks the model can actually see. `_format_candidates`
#    below embeds the candidate excerpts and their real chunk_ids directly
#    in the instruction text sent as `message`, rather than relying on the
#    model to call search_transcripts itself and hope the result set
#    matches `allowed_chunk_ids`/`by_id`. `_parse_outline`'s filter against
#    `allowed_chunk_ids` (real retrieval metadata) still stands as the
#    citations-from-metadata guarantee — this only fixes the model actually
#    having something valid to choose from.
# 2. How Pi's model-driven skill routing (§8.4) picks `ship30-essay` for a
#    call still rests on the instruction text being descriptive enough
#    (PHASE1_INSTRUCTION / _phase2_instruction) — unchanged from before.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from app.config import Settings
from app.errors import ApiError
from app.obs.logging import log_event
from app.services.agent_client import collect_turn_text
from app.services.retrieval import ScoredChunk

TARGET_WORDS = 1250
WORD_TOLERANCE = 100
MIN_HEADINGS = 4
MIN_SOURCES = 3
MAX_SECTION_REPAIR = 1

PHASE1_INSTRUCTION = (
    "Write a Ship 30 essay outline (phase: outline) about the current "
    "conversation topic, using the ship30-essay skill's outline JSON "
    "contract: hook_angle, pattern, sections (4-6, each with heading and "
    "chunk_ids drawn only from the chunk_ids listed below), and takeaway. "
    "Output ONLY the JSON object."
)

MAX_CANDIDATE_CHARS = 600


def _format_candidates(chunks: list[ScoredChunk]) -> str:
    """Render the pre-retrieved candidate set inline in the instruction
    text — the model has no other way to see real chunk_ids or their
    content, since this service takes no context_chunks wire field and
    isn't expected to call search_transcripts for a ship30 phase call."""
    lines = [
        f"[chunk_id={c.chunk_id}] {c.guest} — \"{c.episode_title}\": "
        f"{c.text[:MAX_CANDIDATE_CHARS]}"
        for c in chunks
    ]
    return "Candidate retrieved excerpts (cite only these chunk_ids):\n" + "\n\n".join(lines)


@dataclass
class OutlineSection:
    heading: str
    chunk_ids: list[int]
    is_takeaway: bool = False


@dataclass
class Outline:
    hook_angle: str
    pattern: str
    sections: list[OutlineSection]
    takeaway: str


@dataclass
class ValidationReport:
    ok: bool
    word_count: int
    heading_count: int
    distinct_sources: int
    empty_sections: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class Ship30Result:
    title: str
    content: str
    validation: ValidationReport
    repaired: bool


def _phase2_instruction(heading: str, outline: Outline, is_takeaway: bool) -> str:
    if is_takeaway:
        return (
            f"Write the closing takeaway section (phase: section, takeaway) for "
            f"the Ship 30 essay outlined with hook angle '{outline.hook_angle}'. "
            f"Its mini-headline is '{heading}'. End with one sentence the reader "
            f"could act on today: {outline.takeaway}"
        )
    return (
        f"Write section '{heading}' (phase: section) for the Ship 30 essay "
        f"outlined with hook angle '{outline.hook_angle}' and pattern "
        f"'{outline.pattern}'. Follow the ship30-essay skill's structural "
        f"rules (bolded opening claim, 1/3/1 rhythm, named guest/episode for "
        f"grounded claims). Use only the retrieved chunks you were given."
    )


def _parse_outline(raw: str, allowed_chunk_ids: set[int], trace_id: str) -> Outline:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*)```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ApiError(
            502, "SHIP30_BAD_OUTLINE", f"outline was not valid JSON: {exc}", trace_id=trace_id
        ) from exc

    sections_raw = obj.get("sections", [])
    if not isinstance(sections_raw, list) or not (4 <= len(sections_raw) <= 6):
        raise ApiError(
            502,
            "SHIP30_BAD_OUTLINE",
            f"outline must have 4-6 sections, got {len(sections_raw)}",
            trace_id=trace_id,
        )
    sections = []
    for s in sections_raw:
        ids = [i for i in s.get("chunk_ids", []) if i in allowed_chunk_ids]
        sections.append(OutlineSection(heading=str(s["heading"]), chunk_ids=ids))

    return Outline(
        hook_angle=str(obj.get("hook_angle", "")),
        pattern=str(obj.get("pattern", "")),
        sections=sections,
        takeaway=str(obj.get("takeaway", "")),
    )


async def _generate_outline(
    settings: Settings, trace_id: str, session_id: uuid.UUID, chunks: list[ScoredChunk]
) -> Outline:
    message = f"{PHASE1_INSTRUCTION}\n\n{_format_candidates(chunks)}"
    raw = await collect_turn_text(settings, trace_id, str(session_id), message)
    allowed_ids = {c.chunk_id for c in chunks}
    return _parse_outline(raw, allowed_ids, trace_id)


async def _generate_section(
    settings: Settings,
    trace_id: str,
    session_id: uuid.UUID,
    heading: str,
    outline: Outline,
    section_chunks: list[ScoredChunk],
    is_takeaway: bool,
) -> str:
    instruction = _phase2_instruction(heading, outline, is_takeaway)
    message = f"{instruction}\n\n{_format_candidates(section_chunks)}"
    return await collect_turn_text(settings, trace_id, str(session_id), message)


def _takeaway_heading(takeaway: str) -> str:
    words = takeaway.strip().split()
    return " ".join(words[:10]) if words else "The takeaway"


def _assemble(hook: str, sections: list[tuple[str, str]]) -> str:
    parts = [hook.strip(), ""]
    for heading, prose in sections:
        parts.append(f"## {heading}")
        parts.append("")
        parts.append(prose.strip())
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def _count_headings(doc: str) -> int:
    return len(re.findall(r"^##\s+.+$", doc, re.MULTILINE))


def _count_words(doc: str) -> int:
    return len(re.findall(r"\S+", doc))


def validate(
    doc: str, sections: list[tuple[str, str]], distinct_sources: int
) -> ValidationReport:
    word_count = _count_words(doc)
    heading_count = _count_headings(doc)
    empty = [h for h, p in sections if len(p.strip()) < 20]
    errors: list[str] = []

    if abs(word_count - TARGET_WORDS) > WORD_TOLERANCE:
        errors.append(f"word_count {word_count} outside {TARGET_WORDS}±{WORD_TOLERANCE}")
    if heading_count < MIN_HEADINGS:
        errors.append(f"heading_count {heading_count} < {MIN_HEADINGS}")
    if distinct_sources < MIN_SOURCES:
        errors.append(f"distinct_sources {distinct_sources} < {MIN_SOURCES}")
    if empty:
        errors.append(f"empty sections: {empty}")

    return ValidationReport(
        ok=not errors,
        word_count=word_count,
        heading_count=heading_count,
        distinct_sources=distinct_sources,
        empty_sections=empty,
        errors=errors,
    )


async def generate_ship30_essay(
    settings: Settings,
    trace_id: str,
    session_id: uuid.UUID,
    topic: str,
    wide_chunks: list[ScoredChunk],
    on_stage: Callable[[str, str | None], None] | None = None,
) -> Ship30Result:
    """`wide_chunks` is a larger-than-F1 retrieval set (PRD F3 step 2),
    already computed by services/retrieval.py — this function performs no
    retrieval of its own."""
    if on_stage:
        on_stage("outlining", None)
    outline = await _generate_outline(settings, trace_id, session_id, wide_chunks)

    by_id = {c.chunk_id: c for c in wide_chunks}
    section_specs: list[tuple[str, list[ScoredChunk], bool]] = [
        (s.heading, [by_id[i] for i in s.chunk_ids if i in by_id], False) for s in outline.sections
    ]
    takeaway_heading = _takeaway_heading(outline.takeaway)
    section_specs.append((takeaway_heading, wide_chunks[:2], True))

    generated: list[tuple[str, str]] = []
    for i, (heading, sec_chunks, is_takeaway) in enumerate(section_specs):
        if on_stage:
            on_stage("drafting", f"section {i + 1} of {len(section_specs)}")
        prose = await _generate_section(
            settings, trace_id, session_id, heading, outline, sec_chunks, is_takeaway
        )
        generated.append((heading, prose))

    if on_stage:
        on_stage("assembling", None)

    all_cited_ids = {i for s in outline.sections for i in s.chunk_ids}
    distinct_sources = len({by_id[i].episode_title for i in all_cited_ids if i in by_id})

    doc = _assemble(outline.hook_angle, generated)
    report = validate(doc, generated, distinct_sources)
    repaired = False

    if not report.ok and report.empty_sections and MAX_SECTION_REPAIR > 0:
        failing_heading = report.empty_sections[0]
        idx = next(i for i, (h, _) in enumerate(generated) if h == failing_heading)
        heading, sec_chunks, is_takeaway = section_specs[idx]
        log_event("ship30_repair", trace_id, section=heading)
        prose = await _generate_section(
            settings, trace_id, session_id, heading, outline, sec_chunks, is_takeaway
        )
        generated[idx] = (heading, prose)
        doc = _assemble(outline.hook_angle, generated)
        report = validate(doc, generated, distinct_sources)
        repaired = True

    log_event(
        "ship30_complete",
        trace_id,
        session_id=str(session_id),
        ok=report.ok,
        word_count=report.word_count,
        heading_count=report.heading_count,
        distinct_sources=report.distinct_sources,
        repaired=repaired,
        errors=report.errors,
    )

    title = outline.hook_angle[:80] if outline.hook_angle else topic[:80]
    return Ship30Result(title=title, content=doc, validation=report, repaired=repaired)
