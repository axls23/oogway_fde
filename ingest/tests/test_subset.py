"""Tests for subset.py: curated-subset episode selection via index/ topic
files (PRD §5 conditional scope cut)."""

from __future__ import annotations

from pathlib import Path

from subset import curated_subset_slugs


def _write_index(index_dir: Path, filename: str, slugs: list[str]) -> None:
    lines = ["# topic\n\n"]
    for slug in slugs:
        lines.append(f"- [{slug.replace('-', ' ').title()}](../episodes/{slug}/transcript.md)\n")
    (index_dir / filename).write_text("".join(lines), encoding="utf-8")


def test_curated_subset_union_and_dedup(tmp_path: Path):
    corpus_dir = tmp_path / "corpus"
    index_dir = corpus_dir / "index"
    index_dir.mkdir(parents=True)

    _write_index(index_dir, "product-management.md", ["alice-guest", "bob-guest"])
    _write_index(index_dir, "growth-strategy.md", ["bob-guest", "carol-guest"])
    _write_index(index_dir, "product-market-fit.md", ["dave-guest"])
    _write_index(index_dir, "leadership.md", [])
    # A topic file NOT in the curated set must be ignored.
    _write_index(index_dir, "ai.md", ["eve-guest"])

    slugs = curated_subset_slugs(corpus_dir)

    assert slugs == ["alice-guest", "bob-guest", "carol-guest", "dave-guest"]
    assert "eve-guest" not in slugs


def test_curated_subset_missing_topic_files_are_not_fatal(tmp_path: Path):
    corpus_dir = tmp_path / "corpus"
    index_dir = corpus_dir / "index"
    index_dir.mkdir(parents=True)
    _write_index(index_dir, "leadership.md", ["only-guest"])
    # product-management.md, growth-strategy.md, product-market-fit.md absent.

    slugs = curated_subset_slugs(corpus_dir)
    assert slugs == ["only-guest"]


def test_curated_subset_no_index_dir_returns_empty(tmp_path: Path):
    corpus_dir = tmp_path / "corpus_without_index"
    corpus_dir.mkdir()
    assert curated_subset_slugs(corpus_dir) == []
