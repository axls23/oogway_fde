#!/usr/bin/env python3
"""ingest.py -- corpus ingestion CLI (architecture.md §6).

    python3 ingest.py --episodes all       # full 303-episode corpus
    python3 ingest.py --episodes subset    # curated subset via index/ topic files
    python3 ingest.py --episodes 10        # first N episodes, for a fast smoke test

Pipeline per episode: parse YAML frontmatter -> skip if content_hash
unchanged -> normalize + chunk (speaker-turn aware, ~800 tokens, 15%
overlap) -> embed via Ollama (nomic-embed-text, batched + bounded
concurrency) -> upsert episodes/chunks -> one ingest_runs row per
invocation. Malformed transcripts are logged and skipped; the run
continues (architecture.md §11).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import db
from chunker import Chunk, chunk_turns
from embeddings import EmbeddingError, OllamaEmbedder
from subset import curated_subset_slugs
from transcript import (
    Frontmatter,
    MalformedTranscriptError,
    content_hash as compute_content_hash,
    parse_frontmatter,
    parse_turns,
    split_frontmatter_and_body,
)

logger = logging.getLogger("ingest")

DEFAULT_DATABASE_URL = "postgresql://lenny:lenny@localhost:5432/lenny_growth_assistant"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"  # standalone default; Compose overrides via env
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_BATCH_SIZE = 16
DEFAULT_CONCURRENCY = 6


@dataclass
class EpisodeUnit:
    source_path: str
    frontmatter: Frontmatter
    content_hash: str
    chunks: list[Chunk]


def discover_episode_dirs(corpus_dir: Path) -> list[Path]:
    episodes_dir = corpus_dir / "episodes"
    if not episodes_dir.is_dir():
        raise FileNotFoundError(
            f"corpus episodes directory not found at {episodes_dir} -- "
            f"run `make corpus` first (clones ChatPRD/lennys-podcast-transcripts into ingest/corpus)"
        )
    return sorted(p for p in episodes_dir.iterdir() if p.is_dir())


def select_episode_dirs(corpus_dir: Path, episodes_arg: str) -> list[Path]:
    all_dirs = discover_episode_dirs(corpus_dir)
    if episodes_arg == "all":
        return all_dirs
    if episodes_arg == "subset":
        slugs = set(curated_subset_slugs(corpus_dir))
        if not slugs:
            logger.warning("curated subset resolved to zero episodes -- check ingest/corpus/index/*.md")
        return [d for d in all_dirs if d.name in slugs]
    try:
        n = int(episodes_arg)
    except ValueError:
        raise SystemExit(
            f"--episodes must be 'all', 'subset', or an integer N; got {episodes_arg!r}"
        )
    if n < 0:
        raise SystemExit("--episodes N must be >= 0")
    return all_dirs[:n]


def load_and_chunk_episode(episode_dir: Path, corpus_dir: Path) -> EpisodeUnit | None:
    """Read, parse and chunk one episode. Returns None (logging why) for any
    malformed transcript: missing frontmatter, unparseable YAML, missing
    required fields, undecodable bytes, empty body, or zero turn markers."""
    path = episode_dir / "transcript.md"
    source_path = path.relative_to(corpus_dir).as_posix()

    if not path.exists():
        logger.warning("MALFORMED skip: %s -- transcript.md not found", source_path)
        return None

    raw_bytes = path.read_bytes()
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        logger.warning("MALFORMED skip: %s -- not valid UTF-8: %s", source_path, exc)
        return None

    try:
        fm = parse_frontmatter(raw_text)
        body = split_frontmatter_and_body(raw_text)
        turns = parse_turns(body)
    except MalformedTranscriptError as exc:
        logger.warning("MALFORMED skip: %s -- %s", source_path, exc)
        return None

    chunks = chunk_turns(turns)
    if not chunks:
        logger.warning("MALFORMED skip: %s -- chunking produced zero chunks", source_path)
        return None

    return EpisodeUnit(
        source_path=source_path,
        frontmatter=fm,
        content_hash=compute_content_hash(raw_bytes),
        chunks=chunks,
    )


async def run(args: argparse.Namespace) -> int:
    corpus_dir = Path(args.corpus_dir).resolve()
    episode_dirs = select_episode_dirs(corpus_dir, args.episodes)
    logger.info("selected %d episode(s) for --episodes %s", len(episode_dirs), args.episodes)

    conn = await db.connect(args.database_url)
    run_id = await db.start_ingest_run(conn, args.embed_model)
    logger.info("ingest_runs row %d started (embed_model=%s)", run_id, args.embed_model)

    malformed_count = 0
    unchanged_count = 0
    to_process: list[EpisodeUnit] = []

    try:
        for episode_dir in episode_dirs:
            unit = load_and_chunk_episode(episode_dir, corpus_dir)
            if unit is None:
                malformed_count += 1
                continue

            existing_hash = await db.get_existing_hash(conn, unit.source_path)
            if existing_hash == unit.content_hash:
                unchanged_count += 1
                logger.info("SKIP unchanged: %s (content_hash matches prior run)", unit.source_path)
                continue

            to_process.append(unit)

        total_chunks = sum(len(u.chunks) for u in to_process)
        logger.info(
            "%d episode(s) to (re)embed, %d chunk(s) total, %d unchanged, %d malformed",
            len(to_process),
            total_chunks,
            unchanged_count,
            malformed_count,
        )

        embed_elapsed = 0.0
        if to_process:
            embedder = OllamaEmbedder(
                base_url=args.ollama_base_url,
                model=args.embed_model,
                batch_size=args.batch_size,
                concurrency=args.concurrency,
            )
            all_texts = [c.text for u in to_process for c in u.chunks]

            embed_start = time.monotonic()
            try:
                all_embeddings = await embedder.embed_many(all_texts)
            except EmbeddingError as exc:
                await db.finish_ingest_run(conn, run_id, 0, 0, "failed")
                logger.error("embedding failed, aborting run: %s", exc)
                return 1
            embed_elapsed = time.monotonic() - embed_start

            logger.info(
                "embedded %d chunks in %.1fs (%.1f chunks/sec)",
                len(all_texts),
                embed_elapsed,
                len(all_texts) / embed_elapsed if embed_elapsed > 0 else float("inf"),
            )

            offset = 0
            written_episode_ids: list[int] = []
            for unit in to_process:
                n = len(unit.chunks)
                embeddings_slice = all_embeddings[offset : offset + n]
                offset += n

                episode_id = await db.upsert_episode(conn, unit.frontmatter, unit.source_path, unit.content_hash)
                await db.replace_chunks(conn, episode_id, unit.chunks, embeddings_slice)
                written_episode_ids.append(episode_id)
                logger.info("wrote %s: episode_id=%d chunks=%d", unit.source_path, episode_id, n)

        final_episode_count = len(to_process) + unchanged_count

        # Recount chunks for every episode actually in scope this run
        # (processed + confirmed-unchanged) so the ingest_runs row reflects
        # the true final state, not just what this invocation wrote.
        all_scope_paths = [u.source_path for u in to_process] + [
            p for p in (
                (d / "transcript.md").relative_to(corpus_dir).as_posix() for d in episode_dirs
            )
            if p not in {u.source_path for u in to_process}
        ]
        final_chunk_count = await conn.fetchval(
            "SELECT COUNT(*) FROM chunks c JOIN episodes e ON e.id = c.episode_id WHERE e.source_path = ANY($1::text[])",
            all_scope_paths,
        )

        await db.finish_ingest_run(conn, run_id, final_episode_count, final_chunk_count or 0, "ok")

        print("\n--- ingest summary ---")
        print(f"episodes in scope:       {len(episode_dirs)}")
        print(f"episodes (re)embedded:   {len(to_process)}")
        print(f"episodes unchanged:      {unchanged_count}")
        print(f"episodes malformed:      {malformed_count}")
        print(f"chunks written this run: {total_chunks}")
        print(f"chunks total (in scope): {final_chunk_count}")
        if embed_elapsed > 0:
            print(f"embedding time:          {embed_elapsed:.1f}s ({total_chunks / embed_elapsed:.1f} chunks/sec)")
        print(f"ingest_runs.id:          {run_id} (status=ok)")
        return 0

    except Exception:
        logger.exception("ingest run failed with an unhandled exception")
        await db.finish_ingest_run(conn, run_id, 0, 0, "failed")
        return 1
    finally:
        await conn.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest Lenny's Podcast transcripts into Postgres.")
    parser.add_argument(
        "--episodes",
        required=True,
        help="'all' (full corpus), 'subset' (curated via index/ topic files), or an integer N (first N)",
    )
    parser.add_argument(
        "--corpus-dir",
        default=str(Path(__file__).parent / "corpus"),
        help="path to the cloned corpus repo (default: ./corpus next to this script)",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="Postgres DSN (default: $DATABASE_URL or postgresql://lenny:lenny@localhost:5432/lenny_growth_assistant)",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
        help="Ollama base URL (default: $OLLAMA_BASE_URL or http://127.0.0.1:11434)",
    )
    parser.add_argument(
        "--embed-model",
        default=os.environ.get("EMBED_MODEL", DEFAULT_EMBED_MODEL),
        help="Ollama embedding model name (default: $EMBED_MODEL or nomic-embed-text)",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "INFO"))
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
