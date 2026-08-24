#!/usr/bin/env python3
"""CI gate: reject unpinned dependencies (ADR-007).

- api/requirements.txt: every line must be `name==version` (no `>=`, `~=`, bare names).
- agent/package.json, web/package.json: no `^` or `~` range specifiers in
  dependencies/devDependencies.
- docker-compose.yml: every `image:` should be pinned to a tag at minimum
  (digest pinning is preferred but not required for local dev images).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_requirements(path: Path) -> list[str]:
    if not path.exists():
        return []
    errors = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if not re.match(r"^[A-Za-z0-9_.\-\[\]]+==[A-Za-z0-9_.\-]+$", line):
            errors.append(f"{path.relative_to(ROOT)}:{i}: unpinned or malformed requirement: {line!r}")
    return errors


def check_package_json(path: Path) -> list[str]:
    if not path.exists():
        return []
    errors = []
    data = json.loads(path.read_text())
    for section in ("dependencies", "devDependencies"):
        for name, version in data.get(section, {}).items():
            if re.match(r"^[\^~]", version) or version in {"*", "latest"}:
                errors.append(f"{path.relative_to(ROOT)}: {section}.{name} has a range specifier: {version!r}")
    return errors


def check_compose_images(path: Path) -> list[str]:
    if not path.exists():
        return []
    errors = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        m = re.match(r"^\s*image:\s*(\S+)\s*$", line)
        if m and ":" not in m.group(1).split("/")[-1]:
            errors.append(f"{path.relative_to(ROOT)}:{i}: image without a tag: {m.group(1)!r}")
    return errors


def main() -> int:
    errors: list[str] = []
    errors += check_requirements(ROOT / "api" / "requirements.txt")
    errors += check_package_json(ROOT / "agent" / "package.json")
    errors += check_package_json(ROOT / "web" / "package.json")
    errors += check_compose_images(ROOT / "docker-compose.yml")

    if errors:
        print("Dependency pin check FAILED:\n")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("Dependency pin check: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
