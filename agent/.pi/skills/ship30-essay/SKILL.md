---
name: ship30-essay
description: >
  Turn a grounded conversation thread into a Ship 30 for 30–style essay
  (~1,250 words) with a strong hook, skimmable structure, and claims
  cited back to Lenny's Podcast transcripts. Use when the user asks for
  an essay, post, article, or long-form write-up on the current topic.
---

# Ship 30 for 30 essay skill

Source: ship30for30.com's "How to Start Writing Online" guide (fetched and
extracted 2026-08-24; see `docs/vendor/ship30-principles.md` for the full
extraction). This file encodes the subset of those principles that apply to
a ~1,250-word grounded essay, per PRD §4.2. It is a **structural contract**,
not a style suggestion — `api/app/services/ship30.py` validates the output
against it (word count, heading count, citation coverage) and repairs
sections that fail, so treat every rule below as something that will be
checked.

## Non-negotiable structure

1. **Hook (1 paragraph, no heading).** Follow the guide's curiosity-gap
   pattern: gesture at a surprising outcome or tension *from the retrieved
   transcript material* without resolving it yet. Name who this is for and
   why it matters in the same paragraph — the guide's "WHO / WHAT / WHY in
   the first lines" rule.
2. **4 to 6 sections, each with an H2 heading that is itself a mini-headline**
   (a complete claim, not a label like "Background"). Pick ONE organizing
   pattern for all sections — all Lessons, all Steps, all Mistakes, or all
   Principles — and hold it for the whole piece. Do not mix patterns.
3. **Each section opens with a bolded one-sentence claim**, then 3–5 sentences
   of support (the guide's 1/3/1 paragraph rhythm), then — where the
   retrieved material supports it — a short bulleted list or a one-line
   named example (guest + episode).
4. **A closing takeaway section** (no "Conclusion" heading — use a mini-headline
   that states the takeaway itself). End with one sentence the reader could
   act on today. This is the "specific, useful takeaway" required by PRD §4.2.
5. **Skimmability is mandatory, not decorative:** at least one bulleted list
   per two sections, bold used only on section-opening claims and genuinely
   load-bearing phrases (not decoration), short single-sentence lines
   alternated with fuller paragraphs.

## Grounding rules

- Every named claim, framework, or number must trace to a retrieved chunk.
  When you use a guest's idea, name the guest and episode inline (e.g.,
  "As *Guest Name* put it on *Episode Title*, ...") — this is what the
  citation-coverage validator checks for (≥ 3 distinct sources, AC7).
- If the retrieved material does not support a section you were about to
  write, cut the section rather than filling it with generic advice. A
  4-section essay that is fully grounded beats a 6-section essay with one
  invented section.
- Never invent a guest, episode, or quote. If you are not certain a chunk
  supports a claim, soften the claim or drop it.

## Generation pipeline (orchestrated by `api`, not by you deciding on your own)

You will be called in two phases by `api/app/services/ship30.py`:

1. **Outline phase.** Given the conversation topic and a wide retrieval set,
   emit ONLY a JSON object:
   ```json
   {
     "hook_angle": "one sentence describing the curiosity-gap angle",
     "pattern": "lessons | steps | mistakes | principles",
     "sections": [
       { "heading": "mini-headline claim", "chunk_ids": [123, 456] }
     ],
     "takeaway": "one sentence, the specific useful thing a reader does next"
   }
   ```
   4 to 6 entries in `sections`. Each `chunk_ids` list must be a subset of the
   chunk IDs you were given — do not reference chunks you were not shown.
2. **Section phase.** For each section, given only its `chunk_ids`' text and
   the outline for context, write that section's prose per the structural
   rules above. Return prose only, no JSON, no heading line (the assembler
   adds the heading from the outline).

Word budget: divide 1,250 words across hook (~120), sections (~180 each for
5 sections), and takeaway (~100) as a guide, not a hard per-section rule —
the validator checks the total, not each section.

## What NOT to do

- Do not write a title as an H1 — the UI supplies the title from the artifact
  metadata.
- Do not add a "Sources" or "References" list at the end — citations live
  inline, per the grounding rules above, and separately as UI citation chips.
- Do not use em-dash-heavy "AI voice" filler ("in today's fast-paced world",
  "it's important to note that"). The guide's own editing principle: ship
  clear sentences, don't decorate them.
