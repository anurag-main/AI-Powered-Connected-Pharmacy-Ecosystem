"""Correlation context and log formatting.

The riskiest property here is isolation: a correlation id that leaks between
concurrent requests is worse than no id at all, because it attributes one user's
activity to another's trace.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.context import (
    UNSET,
    current_context,
    get_request_id,
    get_run_id,
    new_id,
    reset_request_id,
    reset_run_id,
    bind_context,
    set_request_id,
    set_run_id,
)
from app.core.logging_config import (
    ConsoleFormatter,
    JsonFormatter,
    install_context_record_factory,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clean_context():
    """Leave the context as we found it, whatever a test does to it."""

    request_token = set_request_id(UNSET)
    run_token = set_run_id(UNSET)
    yield
    reset_request_id(request_token)
    reset_run_id(run_token)


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


def test_new_id_is_short_and_unique():
    ids = {new_id() for _ in range(1000)}

    assert len(ids) == 1000, "collision in 1000 ids"
    assert all(len(value) == 12 for value in ids)


def test_ids_default_to_unset_outside_a_request():
    """A graph invoked from a script has no request id; that must read cleanly
    rather than crash or produce a misleading empty string."""

    assert get_request_id() == UNSET
    assert get_run_id() == UNSET


def test_setting_and_resetting_a_request_id():
    token = set_request_id("abc123")
    assert get_request_id() == "abc123"

    reset_request_id(token)
    assert get_request_id() == UNSET


def test_request_id_and_run_id_are_independent():
    """They answer different questions and must never overwrite one another."""

    set_request_id("req-1")
    set_run_id("run-1")

    assert current_context() == {"request_id": "req-1", "run_id": "run-1"}


# ---------------------------------------------------------------------------
# Isolation — the property that matters most
# ---------------------------------------------------------------------------


def test_concurrent_workers_do_not_share_request_ids():
    """Each worker sets its own id; none may observe another's.

    This is what a module-level global would get wrong, and the bug would only
    appear under concurrent load — exactly when it is hardest to diagnose.
    """

    def worker(index: int) -> str:
        set_request_id(f"req-{index}")
        # Yield the GIL so the workers genuinely interleave.
        for _ in range(1000):
            pass
        return get_request_id()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(worker, range(8)))

    assert results == [f"req-{index}" for index in range(8)]


def test_a_worker_thread_starts_without_the_callers_context():
    """Documents *why* bind_context is needed — a bare thread sees nothing."""

    set_request_id("req-parent")

    with ThreadPoolExecutor(max_workers=1) as executor:
        seen = executor.submit(get_request_id).result()

    assert seen == UNSET


def test_bind_context_carries_ids_into_a_worker_thread():
    """The fix that keeps parallel tool calls correlated to their request."""

    set_request_id("req-parent")
    set_run_id("run-parent")

    with ThreadPoolExecutor(max_workers=1) as executor:
        seen = executor.submit(bind_context(current_context)).result()

    assert seen == {"request_id": "req-parent", "run_id": "run-parent"}


def test_a_worker_cannot_mutate_the_callers_context():
    """`copy_context` gives the worker a copy — writes must not travel back."""

    set_request_id("req-parent")

    def overwrite() -> None:
        set_request_id("req-child")

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(bind_context(overwrite)).result()

    assert get_request_id() == "req-parent"


# ---------------------------------------------------------------------------
# Record factory
# ---------------------------------------------------------------------------


def test_every_record_is_stamped_with_the_current_ids(caplog):
    install_context_record_factory()
    set_request_id("req-9")
    set_run_id("run-9")

    with caplog.at_level(logging.INFO):
        logging.getLogger("test.stamping").info("some_event")

    record = caplog.records[-1]
    assert record.request_id == "req-9"
    assert record.run_id == "run-9"


def test_installing_the_factory_twice_does_not_stack_wrappers():
    install_context_record_factory()
    first = logging.getLogRecordFactory()

    install_context_record_factory()

    assert logging.getLogRecordFactory() is first


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.ai",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="node_completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-1"
    record.run_id = "run-1"
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_one_parseable_object():
    output = JsonFormatter().format(_record(node="planner", duration_ms=742.0))

    payload = json.loads(output)
    assert payload["event"] == "node_completed"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-1"
    assert payload["run_id"] == "run-1"
    assert payload["node"] == "planner"
    assert payload["duration_ms"] == 742.0
    assert "\n" not in output, "a log line must stay on one line"


def test_json_formatter_survives_a_non_serialisable_field():
    """A logging call must never be the thing that breaks a request."""

    from decimal import Decimal

    payload = json.loads(JsonFormatter().format(_record(amount=Decimal("10.50"))))

    assert payload["amount"] == "10.50"


def test_json_formatter_records_the_error_type_on_an_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record()
        record.exc_info = sys.exc_info()
        payload = json.loads(JsonFormatter().format(record))

    assert payload["error_type"] == "ValueError"
    assert "ValueError: boom" in payload["traceback"]


def test_console_formatter_includes_ids_and_fields():
    output = ConsoleFormatter().format(_record(node="planner", duration_ms=742.0))

    assert "node_completed" in output
    assert "req=req-1" in output
    assert "run=run-1" in output
    assert "node=planner" in output
    assert "duration_ms=742.0" in output
