"""Ollama embedding client.

architecture.md §6: embed via Ollama nomic-embed-text (768-d), batched.

Ollama's `/api/embed` endpoint (the current, non-deprecated one -- the older
`/api/embeddings` only takes a single `prompt`) accepts `input` as either a
single string or a list of strings and returns one embedding per input in
one HTTP round trip, so within a batch we get real request-level batching for
free. On top of that we run several batches concurrently (bounded by a
semaphore) rather than serially, since Ollama's HTTP server itself can
overlap embedding requests for a small model like nomic-embed-text.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger("ingest.embeddings")

EMBED_DIMENSIONS = 768  # must match `vector(768)` in contracts/schema.sql

# Nomic's asymmetric-retrieval task instruction for corpus-side (indexed)
# text. Prepended only to the string sent to Ollama's /api/embed -- the
# caller's texts (and, transitively, the stored `chunks.text` column) are
# never mutated. See api/app/services/retrieval.py's SEARCH_QUERY_PREFIX
# for the query-side counterpart.
SEARCH_DOCUMENT_PREFIX = "search_document: "

                resp.raise_for_status()
                break
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    logger.warning(
                        "embedding batch of %d failed (attempt %d/%d): %s -- retrying",
                        len(batch),
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                    )
                    await asyncio.sleep(2 * (attempt + 1))
        else:
            raise EmbeddingError(f"Ollama embedding request failed after {self.max_retries + 1} attempts: {last_exc}") from last_exc

        data = resp.json()
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise EmbeddingError(
                f"Ollama returned {len(vectors) if isinstance(vectors, list) else 'non-list'} "
                f"embeddings for a batch of {len(batch)}"
            )
        for v in vectors:
            if not isinstance(v, list) or len(v) != EMBED_DIMENSIONS:
                raise EmbeddingError(
                    f"Ollama returned an embedding of dimension "
                    f"{len(v) if isinstance(v, list) else 'unknown'}, expected {EMBED_DIMENSIONS}"
                )
        return vectors
