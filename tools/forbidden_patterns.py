#!/usr/bin/env python3
"""CI gate: mechanically scan for the forbidden patterns listed in CLAUDE.md.

Not a substitute for review — a floor. Exits 1 and prints every hit if any
pattern is found outside an allowlisted path.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "dist", ".vite",
    "ingest/corpus", ".tools", "agent-transcripts",
}
SKIP_SUFFIXES = {".lock", ".sql.gz", ".png", ".jpg", ".svg", ".ico", ".woff", ".woff2"}

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("bare except", re.compile(r"^\s*except\s*:\s*$", re.MULTILINE)),
    ("bare except Exception with pass-only body",
     re.compile(r"except\s+Exception\s*:\s*\n\s*pass\b")),
    ("empty catch block", re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}")),
    ("range specifier in package.json dependency",
     re.compile(r'"\s*(dependencies|devDependencies)"\s*:\s*\{[^}]*"[~^]')),
]

FILENAME_EXCLUDE = {"forbidden_patterns.py"}  # this file legitimately contains the patterns as strings


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    if path.name in FILENAME_EXCLUDE:
        return True
    return False


def main() -> int:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip(path.relative_to(ROOT)):
            continue
        if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".json"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in PATTERNS:
            if path.suffix == ".json" and "package.json" not in label and label != "range specifier in package.json dependency":
                continue
            if pattern.search(text):
                hits.append(f"{path.relative_to(ROOT)}: {label}")

    if hits:
        print("Forbidden pattern scan FAILED:\n")
        for hit in hits:
            print(f"  - {hit}")
        return 1

    print("Forbidden pattern scan: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
