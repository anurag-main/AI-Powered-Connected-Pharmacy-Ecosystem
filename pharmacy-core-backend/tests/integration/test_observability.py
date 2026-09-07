"""End-to-end observability: does one request actually produce a followable trace?

The claim being tested is the one that matters in an interview: *given a request id,
I can show you the graph run, every node and tool that executed, how long each took,
and what failed.* These tests assert that chain exists in the logs.

Assertions target event names and the presence of fields, never exact rendered
strings — a formatter tweak should not fail a behavioural test.
"""

from __future__ import annotations

import logging

import pytest

from app.ai.schemas.business_query import BusinessQuery, Dimension, Metric, PlannerOutput
from app.core.middleware import REQUEST_ID_HEADER

pytestmark = pytest.mark.integration

ENDPOINT = "/api/v1/business/analyze"


def events(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records]


def records_named(caplog, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == event]


# ---------------------------------------------------------------------------
# Request id
# ---------------------------------------------------------------------------


def test_every_response_carries_a_request_id(client):
    response = client.get("/health")

    assert response.headers[REQUEST_ID_HEADER]


def test_each_request_gets_a_distinct_id(client):
    """Reusing an id across requests would merge two users' traces."""

    ids = {client.get("/health").headers[REQUEST_ID_HEADER] for _ in range(5)}

    assert len(ids) == 5


def test_a_safe_client_supplied_request_id_is_reused(client):
    """Honouring the client's id is what lets a trace span frontend and backend."""

    response = client.get("/health", headers={REQUEST_ID_HEADER: "frontend-abc-123"})

    assert response.headers[REQUEST_ID_HEADER] == "frontend-abc-123"


@pytest.mark.parametrize(
    ("supplied", "reason"),
    [
        ("has spaces", "spaces are not in the safe charset"),
        ("line\nbreak", "newline would forge a second log line"),
        ("\x1b[31mred", "terminal escape sequence"),
        ("x" * 65, "longer than the 64-char limit"),
        ("semi;colon", "punctuation outside the safe charset"),
    ],
)
def test_an_unsafe_client_request_id_is_replaced(client, supplied, reason):
    """The header reaches log sinks, so it is untrusted input and must be validated."""

    response = client.get("/health", headers={REQUEST_ID_HEADER: supplied})

    assert response.headers[REQUEST_ID_HEADER] != supplied, reason
    assert len(response.headers[REQUEST_ID_HEADER]) == 12


def test_the_request_id_reaches_application_logs(client, caplog):
    with caplog.at_level(logging.INFO):
        response = client.get("/api/v1/medicines")

    request_id = response.headers[REQUEST_ID_HEADER]
    completed = records_named(caplog, "request_completed")

    assert completed
    assert completed[-1].request_id == request_id


def test_request_logging_records_method_status_and_duration(client, caplog):
    with caplog.at_level(logging.INFO):
        client.get("/api/v1/medicines")

    record = records_named(caplog, "request_completed")[-1]

    assert record.method == "GET"
    assert record.status_code == 200
    assert record.duration_ms >= 0


def test_a_validation_failure_is_logged_at_warning(client, caplog):
    """4xx is a client mistake, not a defect — it must not read as an ERROR."""

    with caplog.at_level(logging.INFO):
        client.post(ENDPOINT, json={"question": "hi", "thread_id": "t-1"})

    record = records_named(caplog, "request_completed")[-1]

    assert record.status_code == 422
    assert record.levelno == logging.WARNING


# ---------------------------------------------------------------------------
# Run id, and its relationship to request id and thread id
# ---------------------------------------------------------------------------


def test_an_ai_request_produces_a_run_with_its_own_id(
    client, seeded_app_db, fake_llm, thread_id, caplog
):
    with caplog.at_level(logging.INFO):
        response = client.post(
            ENDPOINT, json={"question": "What were total sales?", "thread_id": thread_id}
        )

    request_id = response.headers[REQUEST_ID_HEADER]
    started = records_named(caplog, "ai_run_started")[-1]

    assert started.run_id != "-"
    assert started.run_id != request_id, "run id must be its own identifier"
    assert started.request_id == request_id, "and must still correlate to the request"
    assert started.thread_id == thread_id, "conversation id is logged, not conflated"


def test_two_requests_on_one_conversation_get_different_run_ids(
    client, seeded_app_db, fake_llm, thread_id, caplog
):
    """One thread_id, many run_ids — the distinction the docs promise."""

    with caplog.at_level(logging.INFO):
        client.post(ENDPOINT, json={"question": "What were total sales?", "thread_id": thread_id})
        client.post(ENDPOINT, json={"question": "And the margin?", "thread_id": thread_id})

    run_ids = {r.run_id for r in records_named(caplog, "ai_run_started")}
    thread_ids = {r.thread_id for r in records_named(caplog, "ai_run_started")}

    assert len(run_ids) == 2
    assert thread_ids == {thread_id}


def test_a_non_ai_request_produces_no_run_id(client, caplog):
    """A plain CRUD call must not invent a graph run."""

    with caplog.at_level(logging.INFO):
        client.get("/api/v1/medicines")

    assert not records_named(caplog, "ai_run_started")
    assert records_named(caplog, "request_completed")[-1].run_id == "-"


# ---------------------------------------------------------------------------
# The full chain
# ---------------------------------------------------------------------------


def test_one_request_yields_a_followable_trace(
    client, seeded_app_db, fake_llm, thread_id, caplog
):
    """The interview demo, asserted: request → run → nodes → tools → completion,
    every line sharing one request id and one run id."""

    fake_llm.responses[PlannerOutput] = PlannerOutput(queries=[BusinessQuery(metric=Metric.SALES), BusinessQuery(metric=Metric.MARGIN)])

    with caplog.at_level(logging.INFO):
        response = client.post(
            ENDPOINT,
            json={"question": "How profitable am I?", "thread_id": thread_id},
        )

    request_id = response.headers[REQUEST_ID_HEADER]
    emitted = events(caplog)

    assert "ai_run_started" in emitted
    assert "ai_run_completed" in emitted
    assert "request_completed" in emitted

    nodes_run = {r.node for r in records_named(caplog, "node_completed")}
    assert {"planner", "fetcher", "analyzer", "reflector", "finalizer"} <= nodes_run

    tools_run = {r.tool for r in records_named(caplog, "tool_completed")}
    assert tools_run == {"sales", "margin"}

    # Everything the run emitted shares one request id and one run id.
    run_lines = [
        r
        for r in caplog.records
        if r.getMessage() in {"ai_run_started", "node_completed", "tool_completed", "ai_run_completed"}
    ]
    assert {r.request_id for r in run_lines} == {request_id}
    assert len({r.run_id for r in run_lines}) == 1


def test_parallel_tool_calls_stay_correlated(
    client, seeded_app_db, fake_llm, thread_id, caplog
):
    """Tools run on worker threads; without bind_context they would log request_id=-.

    This is the regression test for a bug found while writing these tests.
    """

    fake_llm.responses[PlannerOutput] = PlannerOutput(queries=[BusinessQuery(metric=m) for m in Metric])

    with caplog.at_level(logging.INFO):
        response = client.post(
            ENDPOINT, json={"question": "How is the business?", "thread_id": thread_id}
        )

    request_id = response.headers[REQUEST_ID_HEADER]
    tool_records = records_named(caplog, "tool_completed")

    assert len(tool_records) == 5
    assert all(r.request_id == request_id for r in tool_records)
    assert all(r.run_id != "-" for r in tool_records)


def test_every_node_and_tool_reports_a_duration(
    client, seeded_app_db, fake_llm, thread_id, caplog
):
    with caplog.at_level(logging.INFO):
        client.post(ENDPOINT, json={"question": "What were total sales?", "thread_id": thread_id})

    timed = (
        records_named(caplog, "node_completed")
        + records_named(caplog, "tool_completed")
        + records_named(caplog, "ai_run_completed")
    )

    assert timed
    assert all(isinstance(r.duration_ms, float) and r.duration_ms >= 0 for r in timed)


# ---------------------------------------------------------------------------
# Failure observability
# ---------------------------------------------------------------------------


def test_an_llm_failure_is_logged_with_node_and_error_type(
    client, seeded_app_db, fake_llm, thread_id, caplog
):
    fake_llm.error = RuntimeError("provider unavailable")

    with caplog.at_level(logging.INFO):
        with pytest.raises(RuntimeError):
            client.post(
                ENDPOINT,
                json={"question": "What were total sales?", "thread_id": thread_id},
            )

    node_failure = records_named(caplog, "node_failed")[-1]
    assert node_failure.node == "planner", "the failure is attributed to a specific step"
    assert node_failure.error_type == "RuntimeError"
    assert node_failure.exc_info is not None, "the traceback must be preserved"

    run_failure = records_named(caplog, "ai_run_failed")[-1]
    assert run_failure.error_type == "RuntimeError"
    assert run_failure.duration_ms >= 0


def test_a_tool_failure_is_logged_without_killing_the_run(
    client, seeded_app_db, fake_llm, thread_id, caplog, monkeypatch
):
    from app.ai.tools import business_tools

    original = business_tools.execute_business_query

    def flaky(query, **kwargs):
        if query.metric is Metric.MARGIN:
            raise RuntimeError("margin query exploded")
        return original(query, **kwargs)

    monkeypatch.setattr(business_tools, "execute_business_query", flaky)
    fake_llm.responses[PlannerOutput] = PlannerOutput(queries=[BusinessQuery(metric=Metric.SALES), BusinessQuery(metric=Metric.MARGIN)])

    with caplog.at_level(logging.INFO):
        response = client.post(
            ENDPOINT, json={"question": "How profitable am I?", "thread_id": thread_id}
        )

    assert response.status_code == 200, "one bad tool must not fail the request"

    succeeded = {r.tool for r in records_named(caplog, "tool_completed")}
    assert succeeded == {"sales"}, "only the healthy tool reports success"


def test_a_database_failure_surfaces_in_the_logs(
    client, seeded_app_db, fake_llm, thread_id, caplog, monkeypatch
):
    from app.ai.tools import business_tools

    def dead(query, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(business_tools, "execute_business_query", dead)

    with caplog.at_level(logging.INFO):
        response = client.post(
            ENDPOINT, json={"question": "What were total sales?", "thread_id": thread_id}
        )

    assert response.status_code == 200
    assert not records_named(caplog, "tool_completed"), "nothing succeeded"
    # The run still completes — degraded, and visibly so.
    assert records_named(caplog, "ai_run_completed")


# ---------------------------------------------------------------------------
# Sensitive data
# ---------------------------------------------------------------------------


def test_logs_do_not_leak_the_question_or_api_key(
    client, seeded_app_db, fake_llm, thread_id, caplog
):
    """Business questions and credentials must never reach a log sink.

    The question is user content and the key is a secret; both belong in LangSmith or
    nowhere, not in application logs.
    """

    secret_question = "What were total sales for our confidential Pune branch?"

    with caplog.at_level(logging.DEBUG):
        client.post(ENDPOINT, json={"question": secret_question, "thread_id": thread_id})

    blob = "\n".join(
        f"{r.getMessage()} {r.__dict__}" for r in caplog.records
    )

    assert "confidential Pune branch" not in blob
    assert "sk-test-fake-key-not-used" not in blob
