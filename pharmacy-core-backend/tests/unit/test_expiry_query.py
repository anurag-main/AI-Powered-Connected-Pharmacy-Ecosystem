"""ExpiryRiskQuery validation and the expiry tool.

The boundary between the model and the data. As with BusinessQuery, these tests are
as much about what is *impossible* to express as what is allowed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.schemas.expiry_query import (
    MAX_LIMIT,
    MAX_WINDOW_DAYS,
    RISK_ORDER,
    ExpiryRiskQuery,
    RiskLevel,
)
from app.ai.tools.expiry_tools import EXPIRY_TOOLS, get_expiry_risk, run_expiry_risk

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_the_default_query_is_a_sensible_whole_view():
    """"What's at expiry risk?" with no qualifiers must produce something useful."""

    query = ExpiryRiskQuery()

    assert query.window_days == 90
    assert query.risk_level is None
    assert query.include_expired is True
    assert query.medicine_id is None
    assert query.limit == 10


# ---------------------------------------------------------------------------
# What cannot be expressed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, -1, -100, MAX_WINDOW_DAYS + 1, 100_000])
def test_an_out_of_range_window_is_rejected(value):
    with pytest.raises(ValidationError):
        ExpiryRiskQuery(window_days=value)


@pytest.mark.parametrize("value", [0, -1, MAX_LIMIT + 1, 1_000_000])
def test_an_out_of_range_limit_is_rejected(value):
    """A model asking for a million rows must not be able to."""

    with pytest.raises(ValidationError):
        ExpiryRiskQuery(limit=value)


@pytest.mark.parametrize(
    "value",
    ["urgent", "severe", "CRITICAL!", "high risk", "", "critical; DROP TABLE batches"],
)
def test_an_invented_risk_level_is_rejected(value):
    """risk_level is an enum, so a crafted string cannot reach the query."""

    with pytest.raises(ValidationError):
        ExpiryRiskQuery(risk_level=value)


@pytest.mark.parametrize("value", [0, -1, -999])
def test_a_non_positive_medicine_id_is_rejected(value):
    with pytest.raises(ValidationError):
        ExpiryRiskQuery(medicine_id=value)


def test_the_query_exposes_no_free_text_field():
    """Nothing here can carry SQL, a column name or an operator — every field is an
    int, a bool or an enum."""

    for name, field in ExpiryRiskQuery.model_fields.items():
        assert field.annotation is not str, f"{name} accepts free text"


# ---------------------------------------------------------------------------
# What is allowed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", list(RiskLevel))
def test_every_risk_level_is_accepted(level):
    assert ExpiryRiskQuery(risk_level=level).risk_level is level


@pytest.mark.parametrize("window", [1, 7, 30, 90, MAX_WINDOW_DAYS])
def test_reasonable_windows_are_accepted(window):
    assert ExpiryRiskQuery(window_days=window).window_days == window


def test_every_risk_level_has_a_rank():
    """A level missing from RISK_ORDER would raise a KeyError while sorting."""

    assert set(RISK_ORDER) == set(RiskLevel)


def test_risk_levels_rank_worst_first():
    assert (
        RISK_ORDER[RiskLevel.EXPIRED]
        < RISK_ORDER[RiskLevel.CRITICAL]
        < RISK_ORDER[RiskLevel.HIGH]
        < RISK_ORDER[RiskLevel.MEDIUM]
        < RISK_ORDER[RiskLevel.LOW]
    )


def test_describe_reports_shape_without_results():
    """Used in logs, so it must never carry stock levels or money."""

    text = ExpiryRiskQuery(window_days=7, risk_level=RiskLevel.CRITICAL, limit=5).describe()

    assert "window=7d" in text
    assert "risk=critical" in text
    assert "top 5" in text


# ---------------------------------------------------------------------------
# The tool surface
# ---------------------------------------------------------------------------


def test_exactly_one_expiry_tool_is_exposed():
    assert len(EXPIRY_TOOLS) == 1
    assert EXPIRY_TOOLS[0].name == "get_expiry_risk"


def test_the_tool_takes_the_query_fields():
    args = get_expiry_risk.args

    assert {"window_days", "risk_level", "include_expired", "limit"} <= set(args)


def test_the_tool_returns_a_serialisable_report(expiry_db, expiry_as_of):
    """The graph hands this straight to the model as JSON, so it must round-trip."""

    import json

    result = get_expiry_risk.invoke({"window_days": 365, "limit": 100})

    assert json.dumps(result), "the report must be JSON-serialisable"
    assert result["total_batches_reviewed"] == 6


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"window_days": 0}, "window below minimum"),
        ({"window_days": 99999}, "window above maximum"),
        ({"limit": 0}, "limit below minimum"),
        ({"limit": 500}, "limit above maximum"),
        ({"risk_level": "urgent"}, "invented risk level"),
        ({"medicine_id": 0}, "invalid medicine id"),
    ],
)
def test_the_tool_rejects_invalid_arguments(arguments, reason):
    """Validation happens before any database work, so a bad call costs nothing."""

    with pytest.raises(ValidationError):
        get_expiry_risk.invoke(arguments)


def test_run_expiry_risk_honours_the_as_of_date(expiry_db, expiry_as_of):
    """as_of is threaded through so no test depends on the real clock."""

    report = run_expiry_risk(
        ExpiryRiskQuery(window_days=365, limit=100), as_of=expiry_as_of
    )

    assert report.generated_for == expiry_as_of
    assert report.total_batches_reviewed == 6


def test_the_report_states_the_date_it_was_generated_for(expiry_db, expiry_as_of):
    """Without it, a stored or forwarded report is undatable and its "5 days to
    expiry" becomes meaningless."""

    report = run_expiry_risk(ExpiryRiskQuery(), as_of=expiry_as_of)

    assert report.generated_for == expiry_as_of
    assert report.window_days == 90
