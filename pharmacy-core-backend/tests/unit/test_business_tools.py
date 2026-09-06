"""The five BI tools, and the parallel fetcher that drives them.

The tools open their own database session rather than receiving one, so these tests
exercise the real ``SessionLocal`` path — pointed at the temp SQLite file by
``conftest``, not at MySQL.
"""

from __future__ import annotations

import pytest

from app.ai.tools import business_tools
from app.ai.tools.business_tools import (
    TOOL_REGISTRY,
    execute_tool,
    get_business_metrics,
    get_expiry_summary,
    get_margin_summary,
    get_purchase_summary,
    get_return_summary,
    get_sales_summary,
)
from tests.factories import EXPECTED

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Individual tools
# ---------------------------------------------------------------------------


def test_sales_tool_returns_the_repository_figures(seeded_app_db):
    result = get_sales_summary.invoke({})

    assert result["total_sales"] == EXPECTED["sales"]["total_sales"]
    assert result["total_orders"] == EXPECTED["sales"]["total_orders"]


def test_purchase_tool_returns_the_repository_figures(seeded_app_db):
    result = get_purchase_summary.invoke({})

    assert result["total_purchase"] == EXPECTED["purchases"]["total_purchase"]


def test_return_tool_returns_the_repository_figures(seeded_app_db):
    result = get_return_summary.invoke({})

    assert result["total_returns"] == EXPECTED["returns"]["total_returns"]
    assert result["sales_return_amount"] == EXPECTED["returns"]["sales_return_amount"]


def test_expiry_tool_returns_the_repository_figures(seeded_app_db):
    result = get_expiry_summary.invoke({})

    assert result["expired_batches"] == EXPECTED["expiry"]["expired_batches"]
    assert result["expiry_loss"] == EXPECTED["expiry"]["expiry_loss"]


def test_margin_tool_returns_the_repository_figures(seeded_app_db):
    result = get_margin_summary.invoke({})

    assert result["profit_margin_percent"] == EXPECTED["margin"]["profit_margin_percent"]
    assert result["gross_profit"] == EXPECTED["margin"]["gross_profit"]


def test_every_tool_takes_no_arguments():
    """Pins audit finding B10 at the tool boundary.

    The tools expose no date range and no grouping, so the planner has nothing to
    pass even when the user asks for a period. Milestone 4 gives them parameters.
    """

    for name, tool in TOOL_REGISTRY.items():
        assert tool.args == {}, f"{name} gained parameters — update this gap test."


# ---------------------------------------------------------------------------
# Registry / dispatch
# ---------------------------------------------------------------------------


def test_registry_covers_exactly_the_five_capabilities():
    assert set(TOOL_REGISTRY) == {
        "sales",
        "purchases",
        "returns",
        "expiry",
        "margin",
    }


def test_execute_tool_returns_the_task_name_with_its_result(seeded_app_db):
    task, result = execute_tool("sales")

    assert task == "sales"
    assert result["total_sales"] == EXPECTED["sales"]["total_sales"]


def test_execute_tool_rejects_an_unknown_capability():
    """The planner is an LLM and can invent a capability name; it must not pass."""

    with pytest.raises(ValueError, match="Unknown business capability: nonsense"):
        execute_tool("nonsense")


# ---------------------------------------------------------------------------
# Parallel fetch
# ---------------------------------------------------------------------------


def test_get_business_metrics_fetches_every_planned_capability(seeded_app_db):
    metrics = get_business_metrics(["sales", "margin"])

    assert set(metrics) == {"sales", "margin"}
    assert metrics["sales"]["total_sales"] == EXPECTED["sales"]["total_sales"]
    assert metrics["margin"]["cogs"] == EXPECTED["margin"]["cogs"]


def test_get_business_metrics_handles_all_five_concurrently(seeded_app_db):
    """All five run on worker threads, each with its own session."""

    metrics = get_business_metrics(
        ["sales", "purchases", "returns", "expiry", "margin"]
    )

    assert set(metrics) == set(TOOL_REGISTRY)
    assert not any("error" in value for value in metrics.values())


def test_get_business_metrics_returns_empty_for_an_empty_plan():
    """An off-topic question produces an empty plan; that must not be an error."""

    assert get_business_metrics([]) == {}


def test_one_failing_tool_does_not_lose_the_others(seeded_app_db, monkeypatch):
    """Per-tool failure isolation — the property that keeps a partial outage honest.

    A broken tool must surface as an error entry for *that* capability while the
    rest of the plan still returns real figures.
    """

    original = business_tools.execute_tool

    def flaky(task: str):
        if task == "margin":
            raise RuntimeError("margin query exploded")
        return original(task)

    monkeypatch.setattr(business_tools, "execute_tool", flaky)

    metrics = get_business_metrics(["sales", "margin"])

    assert metrics["margin"] == {"error": "margin query exploded"}
    assert metrics["sales"]["total_sales"] == EXPECTED["sales"]["total_sales"]


def test_total_database_outage_reports_errors_rather_than_crashing(
    seeded_app_db, monkeypatch
):
    """Every tool failing must still return a result dict the analyzer can read."""

    def dead(task: str):
        raise RuntimeError("database is down")

    monkeypatch.setattr(business_tools, "execute_tool", dead)

    metrics = get_business_metrics(["sales", "expiry"])

    assert metrics == {
        "sales": {"error": "database is down"},
        "expiry": {"error": "database is down"},
    }


def test_tools_return_zeroed_metrics_on_an_empty_database(db_session):
    """No seed data at all: the tools must report zeros, not blow up."""

    metrics = get_business_metrics(["sales", "margin", "expiry"])

    assert metrics["sales"]["total_orders"] == 0
    assert metrics["margin"]["revenue"] == 0.0
    assert metrics["expiry"]["expired_batches"] == 0
