"""LLM client factory — single dispatch point for every node's LLM access.

get_llm() returns either ChatNVIDIA or ChatOpenAI based on LLM_PROVIDER in .env.
Every node calls this; never construct chat clients elsewhere.

Both clients inherit from BaseChatModel — same .invoke(), .with_structured_output(),
.bind_tools() surface. Node code stays provider-agnostic.
"""
from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from app.ai.config import (
    LLM_PROVIDER,
    MODEL_NAME,
    NVIDIA_API_KEY,
    OPENAI_API_KEY,
    REQUEST_TIMEOUT_SECONDS,
    TEMPERATURE,
)


def _is_placeholder(value: str) -> bool:
    """True if the value is empty or still has a .env placeholder."""
    if not value:
        return True
    placeholders = ("YOUR_", "sk-...", "nvapi-...")
    return value.startswith(placeholders)


def _build_nvidia_client() -> BaseChatModel:
    if _is_placeholder(NVIDIA_API_KEY):
        raise RuntimeError(
            "NVIDIA_API_KEY is not set or still has placeholder. "
            "Edit pharmacy-core-backend/.env — get a key from https://build.nvidia.com"
        )
    # Imported inside the function so a missing langchain-nvidia-ai-endpoints
    # install only matters if you actually try to use the NVIDIA provider.
    from langchain_nvidia_ai_endpoints import ChatNVIDIA

    return ChatNVIDIA(
        model=MODEL_NAME,
        api_key=NVIDIA_API_KEY,
        temperature=TEMPERATURE,
        # ChatNVIDIA accepts max_tokens but not a `timeout` kwarg — the underlying
        # HTTP client handles connection timeouts via NVIDIA_API_BASE retry settings.
    )


def _build_openai_client() -> BaseChatModel:
    if _is_placeholder(OPENAI_API_KEY):
        raise RuntimeError(
            "OPENAI_API_KEY is not set or still has placeholder. "
            "Edit pharmacy-core-backend/.env — get a key from "
            "https://platform.openai.com/api-keys"
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=MODEL_NAME,
        api_key=OPENAI_API_KEY,
        temperature=TEMPERATURE,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Return the project-wide LLM client. Cached across calls.

    Provider is chosen by LLM_PROVIDER env var. Both branches return objects
    sharing the BaseChatModel surface (.invoke, .with_structured_output, .bind_tools)
    so every downstream node is provider-agnostic.
    """
    if LLM_PROVIDER == "nvidia":
        return _build_nvidia_client()
    if LLM_PROVIDER == "openai":
        return _build_openai_client()
    raise RuntimeError(
        f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}. "
        f"Must be 'nvidia' or 'openai' (case-insensitive)."
    )
