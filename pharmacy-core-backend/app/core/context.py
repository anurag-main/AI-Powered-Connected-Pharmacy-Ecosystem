"""Correlation identifiers for the current unit of work.

THREE IDENTIFIERS, THREE DIFFERENT QUESTIONS
--------------------------------------------
``request_id``  Which HTTP call was this?     One per inbound request. Created by
                                              middleware, returned in the
                                              ``X-Request-ID`` response header.
``thread_id``   Which conversation was this?  Supplied by the *client* and stable
                                              across many requests — it is what the
                                              LangGraph checkpointer keys on. Not
                                              stored here: it is a business input
                                              that travels in the request body.
``run_id``      Which graph execution?        One per graph invocation. A request
                                              may produce none (a plain CRUD call)
                                              or one; a conversation produces many
                                              over its lifetime.

So: one thread_id has many request_ids, and each AI request has exactly one run_id.

WHY CONTEXTVARS
---------------
``ContextVar`` is scoped to the current task/thread rather than the process, so two
concurrent requests cannot see each other's ids — the leak that a module-level global
would cause. Values set inside a request do not escape it.

THREADS
-------
Context does **not** propagate into ``ThreadPoolExecutor`` workers automatically. Code
that fans out to threads must carry it explicitly — use :func:`run_with_context`.
"""

from __future__ import annotations

import contextvars
import uuid
from typing import Any, Callable

# "-" reads better in logs than an empty string when there is genuinely no id —
# e.g. a graph invoked from a script rather than from an HTTP request.
UNSET = "-"

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=UNSET
)
_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default=UNSET)


def new_id() -> str:
    """A short correlation id.

    12 hex chars: collision-safe at this scale and short enough to read in a terminal
    and paste into a grep, which is the whole point of a correlation id.
    """

    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# request_id
# ---------------------------------------------------------------------------


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(request_id: str) -> contextvars.Token:
    """Bind a request id. Returns a token the caller must reset in a ``finally``."""

    return _request_id.set(request_id)


def reset_request_id(token: contextvars.Token) -> None:
    _request_id.reset(token)


# ---------------------------------------------------------------------------
# run_id
# ---------------------------------------------------------------------------


def get_run_id() -> str:
    return _run_id.get()


def set_run_id(run_id: str) -> contextvars.Token:
    return _run_id.set(run_id)


def reset_run_id(token: contextvars.Token) -> None:
    _run_id.reset(token)


def current_context() -> dict[str, str]:
    """The correlation fields, ready to merge into a log record's ``extra``."""

    return {"request_id": get_request_id(), "run_id": get_run_id()}


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------


def bind_context(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Callable[[], Any]:
    """Capture the current context and return a callable that replays it elsewhere.

    Use when handing work to a thread::

        executor.submit(bind_context(execute_tool, task))

    ``ContextVar`` values live in the *current* context, and a thread-pool worker
    starts with a fresh, empty one. Without this, every tool the BI fetcher runs in
    parallel would log ``request_id=-``, and the slowest part of the agent would be
    the one part impossible to tie back to the request that caused it.

    **``copy_context()`` runs here, on the calling thread — that is the entire point.**
    Copying it inside the worker would copy the worker's own empty context and
    silently achieve nothing, which is exactly the bug this signature prevents:
    returning a zero-argument callable makes it impossible to defer the copy by
    mistake.
    """

    context = contextvars.copy_context()

    def replay() -> Any:
        return context.run(func, *args, **kwargs)

    return replay
