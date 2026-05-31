"""LLM configuration — single source of truth for provider, model, and API keys.

Reads .env then exposes settings consumed by app/ai/llm.py.
Validation is deferred to llm.get_llm() so this module imports safely even
before any key is set.

To switch providers: set LLM_PROVIDER in .env. No code change.
"""
import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Same minimal loader as app/core/database.py.

    setdefault ensures real shell env vars (CI, Docker, prod) override .env values —
    only fills env vars that aren't already set in the process.
    TODO: extract to app/core/env.py when a third consumer appears.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_load_dotenv(_BACKEND_ROOT / ".env")


# ------------------------------------------------------------------------
# Public settings
# ------------------------------------------------------------------------

# "nvidia" or "openai". Lowercased to allow forgiving casing.
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "nvidia").lower()

# API keys — both kept in env so swapping providers is just LLM_PROVIDER=other.
NVIDIA_API_KEY: str = os.environ.get("NVIDIA_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")

# Provider-specific default model. User can override with AI_MODEL_NAME.
_DEFAULT_MODELS = {
    "nvidia": "mistralai/mistral-nemotron",
    "openai": "gpt-4o-mini",
}
MODEL_NAME: str = os.environ.get(
    "AI_MODEL_NAME",
    _DEFAULT_MODELS.get(LLM_PROVIDER, "gpt-4o-mini"),
)

# Deterministic — billing/extraction must never be creative.
TEMPERATURE: float = 0.0

# Hard timeout per LLM call. Above 30s is almost always a hung connection.
REQUEST_TIMEOUT_SECONDS: int = 30
