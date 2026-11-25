"""Application settings, read once from the environment (and `.env` when present)."""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Literal

from dotenv import load_dotenv

# Hard cap on prompt size: protects the API key's budget from oversized requests.
MAX_PROMPT_CHARS = 10_000
# Most recent messages sent to the model as context; bounds cost on long conversations.
MAX_HISTORY_MESSAGES = 40

Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None = None
    # Supabase project URL, e.g. https://abcd1234.supabase.co
    supabase_url: str | None = None
    # Public key (sb_publishable_... or the legacy anon key). Safe to expose to the browser:
    # Row Level Security, not the key, protects the data.
    supabase_publishable_key: str | None = None
    model: str = "claude-opus-5-5"
    # Opus 5.5 always thinks, and thinking tokens count toward max_tokens.
    max_tokens: int = 16_000
    # Chat app: short answers. Raise to "medium"/"high" for harder prompts.
    effort: Effort = "low"
    # On Vercel the platform serves `public/`; locally FastAPI serves it.
    serve_frontend: bool = True

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)


def normalize_supabase_url(url: str | None) -> str | None:
    """Accept the project root even if pasted with the `/rest/v1` suffix the dashboard shows."""
    url = (url or "").strip().rstrip("/")
    url = url.removesuffix("/rest/v1").rstrip("/")
    return url or None


def load_settings(env: Mapping[str, str]) -> Settings:
    """Build settings from an environment mapping (pure, easy to test)."""
    return Settings(
        anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
        supabase_url=normalize_supabase_url(env.get("SUPABASE_URL")),
        supabase_publishable_key=env.get("SUPABASE_PUBLISHABLE_KEY") or None,
        serve_frontend=not env.get("VERCEL"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # override=True: the project's .env wins over stale shell variables.
    load_dotenv(override=True)
    return load_settings(os.environ)
