"""Structured JSON logging, one line per stage, trace_id on every line.

architecture.md §11: "Structured logs. JSON lines, one per stage, carrying
trace_id, session_id, stage name, duration, and stage-specific fields."
This module gives every caller one function, `log_event`, so the shape of
a log line can't drift between call sites.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from app.config import get_settings

_LOGGER_NAME = "lenny.api"


def configure_logging() -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return  # already configured (e.g. re-imported under pytest)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(get_settings().log_level)
    logger.propagate = False


def log_event(
    stage: str,
    trace_id: str,
    *,
    session_id: str | None = None,
    level: int = logging.INFO,
    duration_ms: float | None = None,
    **fields: Any,
) -> None:
    """Emit one structured JSON log line.

    `stage` names the pipeline step (e.g. "condense", "retrieve",
    "agent_call", "persist", "health_deps"). `**fields` carries
    stage-specific data — condensed query, chunk ids/scores, provider,
    model, token counts, abstained, etc. Never swallow an exception without
    calling this first with the error stage and message (root CLAUDE.md
    forbidden pattern: silent failure).
    """
    logger = logging.getLogger(_LOGGER_NAME)
    payload: dict[str, Any] = {
        "ts": time.time(),
        "stage": stage,
        "trace_id": trace_id,
    }
    if session_id is not None:
        payload["session_id"] = session_id
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 2)
    payload.update(fields)
    logger.log(level, json.dumps(payload, default=str))


class Stopwatch:
    """Tiny helper for stage timing: `with Stopwatch() as sw: ...` then sw.ms."""

    def __enter__(self) -> Stopwatch:
        self._start = time.perf_counter()
        self.ms: float = 0.0
        return self

    def __exit__(self, *exc: object) -> None:
        self.ms = (time.perf_counter() - self._start) * 1000
