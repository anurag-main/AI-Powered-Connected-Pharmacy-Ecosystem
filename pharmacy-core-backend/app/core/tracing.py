"""LangSmith tracing status — reported honestly at startup.

WHAT THE LIBRARY ACTUALLY DOES
------------------------------
Verified against the installed ``langsmith`` (0.8.x), not assumed:

``langsmith.utils.tracing_is_enabled()`` ends with::

    get_env_var("TRACING_V2", default=get_env_var("TRACING", default="")) == "true"

and ``get_env_var(name)`` searches the namespaces ``("LANGSMITH", "LANGCHAIN")`` in
order. So tracing turns on when **any** of these is exactly ``"true"``:

    LANGSMITH_TRACING_V2 · LANGCHAIN_TRACING_V2 · LANGSMITH_TRACING · LANGCHAIN_TRACING

An API key alone does **nothing**. That was the real state of this project before this
module existed: ``LANGCHAIN_API_KEY`` and ``LANGCHAIN_PROJECT`` were set, no tracing
flag was, and therefore not one trace was ever produced — while the earlier QA report
recorded tracing as "configured". Hence :func:`log_tracing_status`, which says out
loud, at every startup, whether traces are actually being sent.

``get_env_var`` is ``lru_cache``d, so the environment must be populated **before** the
first LangChain call. ``app.ai.config`` and ``app.core.database`` both load ``.env`` at
import, which happens during app import, well before any request — but that ordering is
load-bearing, so do not move the ``.env`` load later.

Nothing here sets credentials or turns tracing on by itself: that is the operator's
choice, made in ``.env``. This module only reports and warns.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("app.tracing")

# In the library's own precedence order.
_TRACING_FLAG_VARS = (
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING",
)
_API_KEY_VARS = ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")
_PROJECT_VARS = ("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT")


def _first_set(names: tuple[str, ...]) -> tuple[str | None, str | None]:
    """Return ``(var_name, value)`` for the first of ``names`` with a non-empty value.

    Mirrors ``langsmith.utils.get_env_var`` exactly, including the detail that it
    tests ``value.strip() != ""`` for presence but returns the value **unstripped**.
    """

    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip() != "":
            return name, value
    return None, None


def tracing_status() -> dict[str, object]:
    """Describe the current tracing configuration. Never returns the API key itself."""

    flag_var, flag_value = _first_set(_TRACING_FLAG_VARS)
    key_var, key_value = _first_set(_API_KEY_VARS)
    project_var, project_value = _first_set(_PROJECT_VARS)

    # Exact match, no casefolding and no trimming — because that is what the library
    # does. Being more forgiving here would be worse than useless: this reporter would
    # say "enabled" for LANGSMITH_TRACING="TRUE " while langsmith sent nothing, which
    # is precisely the false reassurance this module exists to eliminate.
    enabled = flag_value == "true"

    return {
        "enabled": enabled,
        "flag_var": flag_var,
        "api_key_present": key_value is not None,
        "api_key_var": key_var,
        # The project name is a label the operator chose, not a credential.
        "project": project_value,
        "project_var": project_var,
        "endpoint": os.environ.get("LANGSMITH_ENDPOINT")
        or os.environ.get("LANGCHAIN_ENDPOINT"),
    }


def log_tracing_status() -> dict[str, object]:
    """Log whether tracing is on, and warn about configurations that look mistaken."""

    status = tracing_status()

    # Never log the key — only whether one exists.
    logger.info(
        "tracing_status",
        extra={
            "tracing_enabled": status["enabled"],
            "project": status["project"],
            "api_key_present": status["api_key_present"],
        },
    )

    if not status["enabled"] and status["api_key_present"]:
        # The exact trap this project fell into.
        logger.warning(
            "tracing_disabled_despite_api_key",
            extra={
                "hint": "set LANGSMITH_TRACING=true in .env to actually send traces",
            },
        )

    if status["enabled"] and not status["api_key_present"]:
        logger.warning(
            "tracing_enabled_without_api_key",
            extra={"hint": "set LANGSMITH_API_KEY in .env; traces will be dropped"},
        )

    return status
