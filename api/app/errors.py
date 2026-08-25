"""The one error envelope shared by every endpoint (architecture.md §5):

    { "error": { "code", "message", "trace_id", "retryable" } }

`ApiError` is the only exception type route handlers should raise for an
expected failure (missing session, provider unreachable, etc.); the global
handler in main.py turns it into that envelope and logs it with trace_id
before responding — no bare `except:`, no swallowed error (root CLAUDE.md).
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """An expected, structured API failure.

    status_code: HTTP status to return.
    code: machine-readable error code, e.g. "OLLAMA_UNREACHABLE".
    retryable: surfaced verbatim in the envelope; drives the UI's retry banner.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        trace_id: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.trace_id = trace_id
        self.retryable = retryable

    def to_envelope(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "trace_id": self.trace_id,
                "retryable": self.retryable,
            }
        }


def not_found(resource: str, trace_id: str) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{resource} not found", trace_id=trace_id)


def provider_unreachable(provider: str, trace_id: str, detail: str = "") -> ApiError:
    msg = f"{provider} is unreachable" + (f": {detail}" if detail else "")
    return ApiError(
        503,
        "PROVIDER_UNREACHABLE" if provider != "ollama" else "OLLAMA_UNREACHABLE",
        msg,
        trace_id=trace_id,
        retryable=True,
    )


def provider_misconfigured(provider: str, trace_id: str) -> ApiError:
    return ApiError(
        503,
        "PROVIDER_MISCONFIGURED",
        f"{provider} is configured but not usable (missing credentials)",
        trace_id=trace_id,
        retryable=False,
    )


def agent_unreachable(trace_id: str, detail: str = "") -> ApiError:
    msg = "agent service is unreachable" + (f": {detail}" if detail else "")
    return ApiError(503, "AGENT_UNREACHABLE", msg, trace_id=trace_id, retryable=True)
