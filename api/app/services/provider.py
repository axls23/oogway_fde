"""Shared provider-readiness guard, used by condense.py and agent_client.py.

ADR-005 / root CLAUDE.md invariant 3: no silent failover. If the operator
has set LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is absent, every
request that would need the cloud provider fails loudly with a structured
503 (api/CLAUDE.md: "do not crash at startup and do not silently use
Ollama instead"). The service itself still boots fine — see
app/main.py + routers/health.py's /config, which reports
`cloud_available: false` in that case.
"""

from __future__ import annotations

from app.config import Settings
from app.errors import ApiError


def assert_provider_ready(settings: Settings, trace_id: str) -> None:
    if settings.llm_provider == "anthropic" and not settings.cloud_available:
        raise ApiError(
            503,
            "PROVIDER_MISCONFIGURED",
            "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set",
            trace_id=trace_id,
            retryable=False,
        )
