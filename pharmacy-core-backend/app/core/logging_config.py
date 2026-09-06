"""Logging setup — one call at startup, then ``logging.getLogger(__name__)`` anywhere.

TWO FORMATS, ONE SET OF FIELDS
------------------------------
``LOG_FORMAT=console`` (default) — aligned and readable while developing::

    21:30:22 INFO  ai.run          ai_run_completed  [req=8f3a1c2b4d5e run=7c1d… ] duration_ms=2870

``LOG_FORMAT=json`` — one JSON object per line, for anything that ships logs::

    {"timestamp": "...", "level": "INFO", "event": "ai_run_completed", ...}

Both carry the same fields, so a query written against one still makes sense in the
other. Correlation ids are pulled from :mod:`app.core.context` by a filter, so no call
site has to remember to pass them.

EVENT NAMES
-----------
Log messages are stable ``snake_case`` event names — ``ai_run_started``,
``tool_completed`` — with the variable parts in ``extra``. Interpolated prose is
readable once and greppable never; an event name plus fields is both.

WHAT MUST NEVER BE LOGGED
-------------------------
API keys, tokens, passwords, ``Authorization`` headers, full prompts, and whole
database rows. Log identifiers, counts, durations and outcomes. See
``docs/observability.md``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from app.core.context import get_request_id, get_run_id

# Fields every LogRecord already has. Anything outside this set was passed by a call
# site in `extra` and is therefore ours to emit.
_STANDARD_RECORD_FIELDS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "taskName", "thread", "threadName",
        "request_id", "run_id",
    }
)

# Ordered first in console output because these are what you scan for.
_LEADING_FIELDS = ("agent", "node", "tool", "duration_ms", "status", "error_type")


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_")
    }


def install_context_record_factory() -> None:
    """Stamp ``request_id`` / ``run_id`` onto every LogRecord at creation.

    A record *factory* rather than a handler filter, deliberately. A filter only runs
    for the handler it is attached to, so records reaching any other handler — a file
    handler someone adds later, or pytest's ``caplog`` — would arrive without the
    correlation ids. Stamping at creation means every record carries them, whoever
    consumes it, and library records get them too.

    Idempotent: wrapping an already-wrapped factory would still work, but the guard
    keeps repeated ``configure_logging()`` calls from building a chain of wrappers.
    """

    current = logging.getLogRecordFactory()

    if getattr(current, "_binds_correlation_ids", False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = current(*args, **kwargs)
        record.request_id = get_request_id()
        record.run_id = get_run_id()
        return record

    factory._binds_correlation_ids = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


class JsonFormatter(logging.Formatter):
    """One JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "run_id": getattr(record, "run_id", "-"),
        }
        payload.update(_extra_fields(record))

        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__
            payload["traceback"] = self.formatException(record.exc_info)

        # default=str so a stray Decimal or datetime cannot make logging raise —
        # a logging call must never be the thing that breaks a request.
        return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    """Aligned, human-scannable single line."""

    def format(self, record: logging.LogRecord) -> str:
        extras = _extra_fields(record)

        ordered = [
            f"{key}={extras.pop(key)}" for key in _LEADING_FIELDS if key in extras
        ]
        ordered += [f"{key}={value}" for key, value in sorted(extras.items())]

        request_id = getattr(record, "request_id", "-")
        run_id = getattr(record, "run_id", "-")

        line = (
            f"{self.formatTime(record, '%H:%M:%S')} "
            f"{record.levelname:<7} "
            f"{record.name:<28} "
            f"{record.getMessage():<24} "
            f"[req={request_id} run={run_id}]"
        )
        if ordered:
            line += " " + " ".join(ordered)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(level: str | None = None, log_format: str | None = None) -> None:
    """Install handlers on the root logger. Idempotent — safe to call twice.

    Reads ``LOG_LEVEL`` (default ``INFO``) and ``LOG_FORMAT`` (``console`` | ``json``,
    default ``console``) unless overridden by the arguments.
    """

    resolved_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    resolved_format = (log_format or os.environ.get("LOG_FORMAT", "console")).lower()

    install_context_record_factory()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if resolved_format == "json" else ConsoleFormatter()
    )

    root = logging.getLogger()
    # Replace rather than append: repeated calls (reload, test setup) would otherwise
    # stack handlers and duplicate every line.
    root.handlers = [handler]
    root.setLevel(resolved_level)

    # Uvicorn installs its own handlers; let ours own the output so every line has the
    # same shape and the same correlation ids.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True

    # These are chatty at DEBUG and say nothing about our own behaviour.
    for name in ("httpx", "httpcore", "urllib3", "openai", "chromadb"):
        logging.getLogger(name).setLevel(
            max(logging.getLevelNamesMapping()[resolved_level], logging.WARNING)
        )
