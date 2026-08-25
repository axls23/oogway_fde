#!/usr/bin/env python3
"""CI gate: agent/.pi/extensions/manifest.json must exactly describe what's
on disk under agent/.pi/extensions/ (root CLAUDE.md invariant #4).

Pi extensions are arbitrary in-process TypeScript that can register any
tool with no sandbox of their own (see agent/src/capabilities.ts). The
manifest is the allowlist that keeps that from silently widening the
model's tool surface; this script re-checks it at CI time, independent of
the runtime check in agent/src/capabilities.ts (verifyExtensions), so drift
is caught before an image is ever built, not just at container boot.

Checks:
- Every .ts/.js file under agent/.pi/extensions/ (excluding manifest.json)
  has a manifest entry, and that entry's sha256 matches the file's current
  content.
- Every manifest entry's `path` points at a file that actually exists.
- The manifest is well-formed JSON with an `extensions` array, each entry
  carrying path/sha256/tools/approvedBy/description.

This does NOT check the *contents* of an approved extension for dangerous
APIs (bash, network, fs) — that's a human review step at PR time, the same
review a change to session.ts's customTools array would get. This script
only guarantees nothing runs that wasn't reviewed and hashed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT_DIR = ROOT / "agent" / ".pi" / "extensions"
MANIFEST_PATH = EXT_DIR / "manifest.json"
REQUIRED_ENTRY_FIELDS = {"path", "sha256", "tools", "approvedBy", "description"}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    data = json.loads(MANIFEST_PATH.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("extensions"), list):
        raise ValueError(f"{MANIFEST_PATH.relative_to(ROOT)} must be {{'extensions': [...]}}")
    return data["extensions"]


def main() -> int:
    errors: list[str] = []

    if not EXT_DIR.exists():
        print("Extension manifest check: skipped (agent/.pi/extensions/ does not exist).")
        return 0

    try:
        entries = load_manifest()
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Extension manifest check FAILED:\n\n  - {exc}")
        return 1

    for i, entry in enumerate(entries):
        missing = REQUIRED_ENTRY_FIELDS - entry.keys()
        if missing:
            errors.append(f"manifest.json extensions[{i}] is missing field(s): {sorted(missing)}")
            continue
        entry_path = EXT_DIR / entry["path"]
        if not entry_path.exists():
            errors.append(f"manifest.json lists {entry['path']!r} but that file does not exist under {EXT_DIR.relative_to(ROOT)}/")
            continue
        actual = sha256_of(entry_path)
        if actual != entry["sha256"]:
            errors.append(
                f"{entry['path']} has drifted from its approved hash "
                f"(manifest: {entry['sha256']}, actual: {actual}) — re-review and update manifest.json"
            )

    manifest_paths = {e["path"] for e in entries if "path" in e}
    on_disk = [
        p.relative_to(EXT_DIR).as_posix()
        for p in EXT_DIR.rglob("*")
        if p.is_file() and p.suffix in (".ts", ".js") and p.name != "manifest.json"
    ]
    for rel in on_disk:
        if rel not in manifest_paths:
            errors.append(
                f"{rel} exists under agent/.pi/extensions/ but has no manifest.json entry — "
                f"add one (path, sha256, approved tool names, approvedBy) before it can load."
            )

    if errors:
        print("Extension manifest check FAILED:\n")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"Extension manifest check: clean ({len(entries)} approved extension(s), {len(on_disk)} file(s) on disk).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
