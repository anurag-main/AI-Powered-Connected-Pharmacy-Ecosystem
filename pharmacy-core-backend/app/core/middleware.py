"""HTTP middleware: correlation id + access logging.

Every inbound request gets a ``request_id`` bound to the context for the duration of
the call, echoed back in the ``X-Request-ID`` response header, and stamped onto every
log line the request produces — including lines from deep inside the LangGraph nodes.
"""

from __future__ import annotations

import logging
import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import new_id, reset_request_id, set_request_id

logger = logging.getLogger("app.http")

REQUEST_ID_HEADER = "X-Request-ID"

# An inbound id is echoed into every log line and into the response header, so it is
# untrusted input reaching a log sink. Accept only short, boring tokens: this blocks
# log forging via newlines, terminal escape sequences, and unbounded values.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Health checks are polled constantly and would drown everything else.
_UNLOGGED_PATHS = frozenset({"/health"})


def _resolve_request_id(request: Request) -> str:
    """Reuse the client's id when it is safe, otherwise mint our own.

    THE RULE: an ``X-Request-ID`` header is honoured only if it matches
    ``[A-Za-z0-9_-]{1,64}``. Anything else — too long, wrong characters, missing —
    is replaced by a freshly generated id. Honouring a caller's id is what lets a
    trace span the frontend and the backend; validating it is what stops that
    becoming a log-injection hole.
    """

    candidate = request.headers.get(REQUEST_ID_HEADER)

    if candidate and _SAFE_REQUEST_ID.match(candidate):
        return candidate

    return new_id()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id, time the request, log the outcome."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _resolve_request_id(request)
        token = set_request_id(request_id)
        started = time.perf_counter()

        # Route template ("/api/v1/medicines/{medicine_id}") is not known until the
        # router has matched, so the raw path is what we have here. It is logged as
        # a field rather than interpolated into the message so high-cardinality paths
        # never fragment the event name.
        path = request.url.path
        should_log = path not in _UNLOGGED_PATHS

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            # .exception() keeps the traceback — the single most useful thing in the
            # log when a request blew up.
            logger.exception(
                "request_failed",
                extra={
                    "method": request.method,
                    "path": path,
                    "duration_ms": duration_ms,
                    "error_type": type(exc).__name__,
                },
            )
            reset_request_id(token)
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers[REQUEST_ID_HEADER] = request_id

        if should_log:
            # A 5xx is a defect; a 4xx is usually a client mistake. Different levels
            # so an alert can key on ERROR without drowning in validation failures.
            level = (
                logging.ERROR
                if response.status_code >= 500
                else logging.WARNING
                if response.status_code >= 400
                else logging.INFO
            )
            logger.log(
                level,
                "request_completed",
                extra={
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

        reset_request_id(token)
        return response
