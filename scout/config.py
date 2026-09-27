"""Runtime configuration for Scout.

Everything is read from environment variables (optionally loaded from a local
`.env` file that is never committed). No identifiers or keys live in code.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SCOUT_DATA_DIR", ROOT / "data"))
CACHE_DIR = DATA_DIR / "cache"
RUNS_DIR = DATA_DIR / "runs"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines, # comments). Does not override
    variables that are already set in the environment."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")

for _d in (CACHE_DIR, RUNS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class Settings:
    """Snapshot of the configuration at import time (re-read `.env` by
    restarting the process)."""

    # --- Oriane -------------------------------------------------------------
    ORIANE_BASE_URL = env("ORIANE_BASE_URL", "https://connect.oriane.xyz")
    ORIANE_API_KEY = env("ORIANE_API_KEY")
    # auto | bearer | x-api-key | api-key | authorization-raw
    ORIANE_AUTH_STYLE = env("ORIANE_AUTH_STYLE", "auto")
    ORIANE_TIMEOUT_S = float(env("ORIANE_TIMEOUT_S", "45"))
    # Serve only from the on-disk cache (demo plan B when the network is down).
    SCOUT_OFFLINE = env_bool("SCOUT_OFFLINE", False)
    # Use the bundled mock server instead of the real API (dev / rehearsal).
    SCOUT_MOCK = env_bool("SCOUT_MOCK", False)
    # Cache TTL in seconds (default: 3 days; the hackathon lasts one).
    SCOUT_CACHE_TTL_S = env_int("SCOUT_CACHE_TTL_S", 3 * 24 * 3600)

    # --- Budget guards ------------------------------------------------------
    # Hard stop: the client refuses to fetch more results than this per run.
    SCOUT_MAX_RESULTS_PER_RUN = env_int("SCOUT_MAX_RESULTS_PER_RUN", 400)
    SCOUT_DISCOVERY_LIMIT = env_int("SCOUT_DISCOVERY_LIMIT", 100)
    SCOUT_VET_TOP_K = env_int("SCOUT_VET_TOP_K", 6)
    SCOUT_VET_VIDEOS_PER_CREATOR = env_int("SCOUT_VET_VIDEOS_PER_CREATOR", 12)

    # --- LLM ----------------------------------------------------------------
    # auto | anthropic | claude-cli | ollama | none
    SCOUT_LLM_BACKEND = env("SCOUT_LLM_BACKEND", "auto")
    ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
    SCOUT_ANTHROPIC_MODEL = env("SCOUT_ANTHROPIC_MODEL", "claude-sonnet-5")
    SCOUT_CLAUDE_CLI_MODEL = env("SCOUT_CLAUDE_CLI_MODEL", "sonnet")
    OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    SCOUT_OLLAMA_MODEL = env("SCOUT_OLLAMA_MODEL", "qwen3.5:9b")
    SCOUT_LLM_TIMEOUT_S = float(env("SCOUT_LLM_TIMEOUT_S", "90"))

    # --- App ----------------------------------------------------------------
    SCOUT_HOST = env("SCOUT_HOST", "127.0.0.1")
    SCOUT_PORT = env_int("SCOUT_PORT", 8787)
    SCOUT_PUBLIC_URL = env("SCOUT_PUBLIC_URL")  # e.g. a tunnel URL for demo links


settings = Settings()
