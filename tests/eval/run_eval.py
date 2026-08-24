#!/usr/bin/env python3
"""Run the fixed evaluation set (PRD §3, AC2/AC3) against a live api service.

Usage:
    python3 run_eval.py [--base-url http://localhost:8000]

For each in-corpus question: creates a session, posts the message, consumes
the SSE stream, and prints the answer plus its citations for a HUMAN to grade
against the grounded_answer_rate rubric (PRD §3 — "at least one cited chunk
substantively supports the claim" is a judgment call this script cannot make
alone). What it DOES assert mechanically:

  - every in-corpus question returns >=1 citation and abstained=false
    (a necessary, not sufficient, condition for a grounded answer — this
    catches total retrieval failure, not weak grounding)
  - every out-of-corpus question returns abstained=true (AC3, fully
    mechanical — a confident answer here is an unambiguous failure)

Exits non-zero if the AC3 guardrail fails (that one has no human judgment
call attached: 5/5 or the build has a real fabrication risk).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def run_turn(base_url: str, session_id: str, content: str) -> dict:
    """POST a message and consume the SSE stream, returning a summary dict."""
    req = urllib.request.Request(
        f"{base_url}/sessions/{session_id}/messages",
        data=json.dumps({"content": content}).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    citations: list[dict] = []
    text_parts: list[str] = []
    abstained = False
    with urllib.request.urlopen(req, timeout=120) as resp:
        event = None
        for raw_line in resp:
            line = raw_line.decode().rstrip("\n")
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event:
                data = json.loads(line.split(":", 1)[1].strip())
                if event == "token":
                    text_parts.append(data.get("text", ""))
                elif event == "citation":
                    citations.append(data)
                elif event == "done":
                    abstained = bool(data.get("abstained", False))
    return {"text": "".join(text_parts), "citations": citations, "abstained": abstained}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    questions = yaml.safe_load((HERE / "questions.yaml").read_text())

    try:
        urllib.request.urlopen(f"{args.base_url}/health", timeout=5)
    except urllib.error.URLError as e:
        print(f"api not reachable at {args.base_url}: {e}", file=sys.stderr)
        print("Start it with `make up` (or run api standalone) before running the eval.", file=sys.stderr)
        return 2

    session = post_json(f"{args.base_url}/sessions", {"title": "eval run"})
    session_id = session["id"]

    print(f"\n=== In-corpus questions ({len(questions['in_corpus'])}) — grade grounded_answer_rate by hand ===\n")
    weak = 0
    for q in questions["in_corpus"]:
        result = run_turn(args.base_url, session_id, q["question"])
        n_cites = len(result["citations"])
        flag = "OK" if n_cites >= 1 and not result["abstained"] else "WEAK/ABSTAINED"
        if flag != "OK":
            weak += 1
        print(f"[{q['id']}] {flag}  citations={n_cites}  abstained={result['abstained']}")
        print(f"  Q: {q['question']}")
        print(f"  A: {result['text'][:220]}{'...' if len(result['text']) > 220 else ''}")
        for c in result["citations"][:3]:
            print(f"    - {c.get('guest', '?')} — {c.get('episode', '?')} (score={c.get('score', '?')})")
        print()

    print(f"\n=== Out-of-corpus questions ({len(questions['out_of_corpus'])}) — must ALL abstain (AC3) ===\n")
    ac3_failures = 0
    for q in questions["out_of_corpus"]:
        result = run_turn(args.base_url, session_id, q["question"])
        ok = result["abstained"]
        if not ok:
            ac3_failures += 1
        print(f"[{q['id']}] {'ABSTAINED (correct)' if ok else 'FAILED — ANSWERED OUT-OF-CORPUS QUESTION'}")
        print(f"  Q: {q['question']}")
        if not ok:
            print(f"  A: {result['text'][:220]}")
        print()

    print("=" * 70)
    print(f"In-corpus: {len(questions['in_corpus']) - weak}/{len(questions['in_corpus'])} returned citations without abstaining (necessary, not sufficient — grade grounding by hand)")
    print(f"AC3 guardrail: {len(questions['out_of_corpus']) - ac3_failures}/{len(questions['out_of_corpus'])} correctly abstained")

    return 1 if ac3_failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
