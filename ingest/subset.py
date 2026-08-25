"""Curated-subset episode selection via the corpus's own index/ topic files.

PRD §5 conditional scope cut: if full ingest exceeds the time budget, ship
the seeded index from a curated subset selected via `index/product-management.md`,
`index/growth-strategy.md`, `index/product-market-fit.md`, `index/leadership.md`
-- the four topics named explicitly in the PRD.

Format (verified against the real corpus, 2026-08-24): each topic file is a
flat markdown list, one episode per line:
    - [Guest Name](../episodes/{slug}/transcript.md)
"""

from __future__ import annotations

import re
from pathlib import Path

SUBSET_TOPICS = [
    "product-management.md",
    "growth-strategy.md",
    "product-market-fit.md",
    "leadership.md",
]

_EPISODE_LINK_RE = re.compile(r"\.\./episodes/([A-Za-z0-9_-]+)/transcript\.md")


def curated_subset_slugs(corpus_dir: Path) -> list[str]:
    """Return the sorted, de-duplicated set of episode slugs referenced by
    any of SUBSET_TOPICS. Missing topic files are logged by the caller and
    simply contribute nothing -- not fatal, since the corpus's index/ folder
    is generated content the ingest pipeline doesn't own."""
    slugs: set[str] = set()
    index_dir = corpus_dir / "index"
    for topic_file in SUBSET_TOPICS:
        path = index_dir / topic_file
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        slugs.update(_EPISODE_LINK_RE.findall(text))
    return sorted(slugs)
