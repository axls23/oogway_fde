"""trace_id generation and propagation.

Choice: UUID4, generated at the `api` edge (one per incoming turn), not a
ULID. Both are acceptable per architecture.md §11 ("ULID or UUID4, your
call, document it"); UUID4 is chosen because it needs no extra dependency
(stdlib `uuid`) and every other identifier in the schema (sessions,
messages, artifacts) is already a UUID, so trace_id fits the same shape as
everything a log line sits next to. The trade-off given up is ULID's
lexicographic sortability-by-time, which nothing here depends on — traces
are looked up by exact value (grep), not range-scanned.

The trace_id is threaded through condensation -> retrieval -> agent call ->
persistence by passing it explicitly as a function argument at each stage
(see services/*.py), not via contextvars/thread-locals — explicit threading
keeps it visible in every function signature that needs it, which matters
more here than the convenience of an ambient global in an async codebase
where implicit context can leak across concurrent requests.
"""

from __future__ import annotations

import uuid


def new_trace_id() -> str:
    return uuid.uuid4().hex
