"""Instrumentation for AI execution: runs, nodes, tools, and LLM calls.

Four seams, chosen because they are the four questions asked when an agent misbehaves:

    ai_run_*      Did the agent run, how long did the whole thing take, did it fail?
    node_*        Which step was slow or broke?
    tool_*        Which data fetch was slow or broke?
    llm_*         Which model call, how long, how many tokens?

Everything here is additive — it logs and re-raises. No wrapper swallows an exception
or alters a return value, so instrumenting a node cannot change what the graph does.

Node and tool instrumentation is applied where the graph is *assembled* rather than
inside each node, so node modules stay free of logging boilerplate and the list of
what is instrumented is readable in one place.
"""

from __future__ import annotations

import functools
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.context import new_id, reset_run_id, set_run_id

logger = logging.getLogger("app.ai")


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


@contextmanager
def ai_run(agent: str, thread_id: str | None = None) -> Iterator[str]:
    """Bracket one graph invocation. Yields the generated ``run_id``.

        with ai_run("business", thread_id=request.thread_id) as run_id:
            state = graph.invoke(...)

    The ``run_id`` is bound to the context for the duration, so every node, tool and
    LLM log line inside the block carries it without being told.

    ``thread_id`` is logged, never bound: it identifies a *conversation*, which spans
    many runs. Keeping it out of the context makes it impossible to confuse the two.
    """

    run_id = new_id()
    token = set_run_id(run_id)
    started = time.perf_counter()

    logger.info("ai_run_started", extra={"agent": agent, "thread_id": thread_id})

    try:
        yield run_id
    except Exception as exc:
        logger.exception(
            "ai_run_failed",
            extra={
                "agent": agent,
                "thread_id": thread_id,
                "duration_ms": _elapsed_ms(started),
                "error_type": type(exc).__name__,
            },
        )
        raise
    else:
        logger.info(
            "ai_run_completed",
            extra={
                "agent": agent,
                "thread_id": thread_id,
                "duration_ms": _elapsed_ms(started),
            },
        )
    finally:
        reset_run_id(token)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def observe_node(name: str, agent: str) -> Callable[[Callable], Callable]:
    """Wrap a LangGraph node so it logs its start, duration and outcome.

    ``functools.wraps`` matters more than usual here: LangGraph inspects a node's
    signature to decide whether to pass ``config`` as a second argument. ``wraps``
    sets ``__wrapped__``, which ``inspect.signature`` follows, so the wrapper keeps
    reporting the original signature and single- and two-argument nodes both work.
    """

    def decorate(node: Callable) -> Callable:
        @functools.wraps(node)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            logger.debug("node_started", extra={"agent": agent, "node": name})

            try:
                result = node(*args, **kwargs)
            except Exception as exc:
                logger.exception(
                    "node_failed",
                    extra={
                        "agent": agent,
                        "node": name,
                        "duration_ms": _elapsed_ms(started),
                        "error_type": type(exc).__name__,
                    },
                )
                raise

            logger.info(
                "node_completed",
                extra={
                    "agent": agent,
                    "node": name,
                    "duration_ms": _elapsed_ms(started),
                },
            )
            return result

        return wrapper

    return decorate


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@contextmanager
def observe_tool(name: str) -> Iterator[None]:
    """Bracket one tool execution.

    Deliberately logs the tool *name* and outcome, never its arguments or result: a
    business tool returns real pharmacy figures, and a log sink is the wrong place
    for them. Identifiers, durations and outcomes are what debugging needs.
    """

    started = time.perf_counter()
    logger.debug("tool_started", extra={"tool": name})

    try:
        yield
    except Exception as exc:
        logger.warning(
            "tool_failed",
            extra={
                "tool": name,
                "duration_ms": _elapsed_ms(started),
                "status": "error",
                "error_type": type(exc).__name__,
            },
        )
        raise

    logger.info(
        "tool_completed",
        extra={"tool": name, "duration_ms": _elapsed_ms(started), "status": "success"},
    )


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------


class LLMObservabilityHandler(BaseCallbackHandler):
    """LangChain callback that times model calls and records token usage.

    Registered once on the client in ``app.ai.llm``, so every node's call is covered
    without any node knowing about it.

    Token counts are reported **only when the provider actually returns them**. There
    is no estimation and no tokenizer fallback: an invented number in a cost dashboard
    is worse than an absent one.

    Prompts are never logged. They routinely contain business data, and the whole
    prompt is what LangSmith is for.
    """

    def __init__(self) -> None:
        # Keyed by LangChain's per-call run id (its own UUID, unrelated to our run_id),
        # so overlapping calls cannot mix up their start times.
        self._started: dict[UUID, float] = {}

    def on_llm_start(self, serialized, prompts, *, run_id: UUID, **kwargs: Any) -> None:
        self._started[run_id] = time.perf_counter()

    def on_chat_model_start(
        self, serialized, messages, *, run_id: UUID, **kwargs: Any
    ) -> None:
        # Chat models emit this instead of on_llm_start.
        self._started[run_id] = time.perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        duration_ms = self._take_duration(run_id)
        extra: dict[str, Any] = {"duration_ms": duration_ms, "status": "success"}
        extra.update(_usage_fields(response))

        logger.info("llm_completed", extra=extra)

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        logger.warning(
            "llm_failed",
            extra={
                "duration_ms": self._take_duration(run_id),
                "status": "error",
                "error_type": type(error).__name__,
            },
        )

    def _take_duration(self, run_id: UUID) -> float | None:
        started = self._started.pop(run_id, None)
        return _elapsed_ms(started) if started is not None else None


def _usage_fields(response: LLMResult) -> dict[str, Any]:
    """Pull model name and token counts out of a provider response, if present.

    Providers disagree about where this lives, and some omit it entirely. Every lookup
    is defensive, and a miss simply means the field is absent from the log line.
    """

    fields: dict[str, Any] = {}
    output = response.llm_output or {}

    model = output.get("model_name") or output.get("model")
    if model:
        fields["model"] = model

    usage = output.get("token_usage") or output.get("usage") or {}

    # Newer LangChain surfaces usage on the message rather than in llm_output.
    if not usage:
        try:
            message = response.generations[0][0].message  # type: ignore[union-attr]
            usage = getattr(message, "usage_metadata", None) or {}
            if not model:
                metadata = getattr(message, "response_metadata", {}) or {}
                if metadata.get("model_name"):
                    fields["model"] = metadata["model_name"]
        except (AttributeError, IndexError):
            usage = {}

    prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
    completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")

    if prompt_tokens is not None:
        fields["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        fields["completion_tokens"] = completion_tokens
    if total_tokens is not None:
        fields["total_tokens"] = total_tokens

    return fields
