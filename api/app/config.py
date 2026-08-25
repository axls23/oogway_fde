"""Settings loaded from environment variables.

Every field here must have a corresponding entry in `.env.example` at the
repo root (root CLAUDE.md forbidden-pattern: "environment variables used in
code but not documented in .env.example"). Nothing here has a default that
silently changes product behavior in a way `.env.example` doesn't already
document — e.g. LLM_PROVIDER defaults to "ollama" because that's what
.env.example ships uncommented.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["ollama", "anthropic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── LLM provider toggle ──────────────────────────────────────────────
    llm_provider: Provider = "ollama"
    llm_model: str = "qwen2.5:7b-instruct"
    anthropic_api_key: str | None = None

    # ── Ollama ────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://host.docker.internal:11434"
    embed_model: str = "nomic-embed-text"

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://lenny:lenny@localhost:5432/lenny_growth_assistant"
    )

    # ── Retrieval tuning ──────────────────────────────────────────────────
    retrieval_floor: float = 0.45
    top_k_default: int = 8
    return_n: int = 4
    session_boost: float = 0.05

    # ── Internal service auth ────────────────────────────────────────────
    agent_internal_token: str = "dev-local-only-change-me"

    # ── Agent service ─────────────────────────────────────────────────────
    # Not in .env.example because it's set by docker-compose.yml directly
    # (`AGENT_BASE_URL: http://agent:8100`); documented there and in
    # architecture.md §2. Defaulted here so `api` still boots standalone
    # (e.g. under pytest) without Compose.
    agent_base_url: str = "http://localhost:8100"

    # ── Timeouts / resilience ────────────────────────────────────────────
    model_timeout_s: int = 60

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── CORS ──────────────────────────────────────────────────────────────
    # `web` (localhost:5173) and `api` (localhost:8000) are different
    # origins to a browser even on one machine — without this, every fetch
    # from the UI is silently blocked by the browser, not logged anywhere
    # server-side (GET /config -> "provider unknown", POST /sessions ->
    # chat can't start). Comma-separated exact origins, no wildcard: this
    # app is a local single-user demo, not a public API.
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cloud_available(self) -> bool:
        return self.anthropic_api_key is not None and self.anthropic_api_key != ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Internal tuning constant, not an environment variable: how many prior
# turns (user+assistant messages) feed the condensation prompt. Kept as a
# plain constant rather than a Settings field so it never needs an
# .env.example entry (root CLAUDE.md forbidden pattern).
CONDENSE_HISTORY_TURNS = 6
