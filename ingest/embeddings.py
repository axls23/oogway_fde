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


class EmbeddingError(RuntimeError):
    """Raised when Ollama is unreachable or returns something we can't use."""


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        batch_size: int = 16,
        concurrency: int = 6,
        timeout_s: float = 600.0,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.batch_size = batch_size
        self.concurrency = concurrency
        self.timeout_s = timeout_s
        self.max_retries = max_retries

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, preserving order, via bounded-concurrency
        batched requests to /api/embed."""
        if not texts:
            return []

        batches: list[list[str]] = [
            texts[i : i + self.batch_size] for i in range(0, len(texts), self.batch_size)
        ]
        semaphore = asyncio.Semaphore(self.concurrency)
        results: list[list[list[float]] | None] = [None] * len(batches)

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:

            async def run_batch(idx: int, batch: list[str]) -> None:
                async with semaphore:
                    results[idx] = await self._embed_batch(client, batch)

            await asyncio.gather(*(run_batch(i, b) for i, b in enumerate(batches)))

        embeddings: list[list[float]] = []
        for batch_result in results:
            assert batch_result is not None
            embeddings.extend(batch_result)
        return embeddings

    async def _embed_batch(self, client: httpx.AsyncClient, batch: list[str]) -> list[list[float]]:
        """POST one batch to /api/embed, retrying transient failures
        (timeouts, connection resets) up to `max_retries` times with a
        short linear backoff before giving up."""
        url = f"{self.base_url}/api/embed"
        last_exc: httpx.HTTPError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.post(url, json={"model": self.model, "input": batch})
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
