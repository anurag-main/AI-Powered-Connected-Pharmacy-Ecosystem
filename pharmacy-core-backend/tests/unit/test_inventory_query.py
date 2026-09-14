"""InventoryRiskQuery — the security boundary between the model and the database.

The planner's output is the only thing an LLM contributes to what gets executed. If a
field here were free text, an unbounded integer or an open string, the model's
mistakes would reach the service. Every test below is about what the contract
*refuses*, not about what it allows.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.schemas.inventory_query import (
    MAX_LIMIT,
    MAX_TARGET_COVER_DAYS,
    MIN_TARGET_COVER_DAYS,
    InventoryRiskLevel,
    InventoryRiskQuery,
    InventorySort,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_an_empty_query_is_valid_and_sensible():
    """A question with no severity and no amount must not force the planner to
    invent one."""

    query = InventoryRiskQuery()

    assert query.target_cover_days == 60
    assert query.risk_level is None
    assert query.min_capital_at_risk == 0.0
    assert query.medicine_id is None
    assert query.sort is InventorySort.RISK
    assert query.limit == 10


# ---------------------------------------------------------------------------
# target_cover_days
# ---------------------------------------------------------------------------


def test_target_cover_accepts_its_bounds():
    assert InventoryRiskQuery(target_cover_days=MIN_TARGET_COVER_DAYS).target_cover_days == 7
    assert (
        InventoryRiskQuery(target_cover_days=MAX_TARGET_COVER_DAYS).target_cover_days
        == 365
    )


def test_target_cover_below_the_floor_is_rejected():
    """A one-day target would make almost every medicine critical and the report
    useless."""

    with pytest.raises(ValidationError):
        InventoryRiskQuery(target_cover_days=1)


def test_target_cover_above_the_ceiling_is_rejected():
    with pytest.raises(ValidationError):
        InventoryRiskQuery(target_cover_days=366)


def test_a_negative_target_cover_is_rejected():
    with pytest.raises(ValidationError):
        InventoryRiskQuery(target_cover_days=-30)


def test_a_non_numeric_target_cover_is_rejected():
    with pytest.raises(ValidationError):
        InventoryRiskQuery(target_cover_days="two months")


# ---------------------------------------------------------------------------
# risk_level
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", [l.value for l in InventoryRiskLevel])
def test_every_declared_risk_level_is_accepted(level):
    assert InventoryRiskQuery(risk_level=level).risk_level.value == level


def test_an_invented_risk_level_is_rejected():
    """The model will occasionally produce a plausible-sounding level that does not
    exist. It must fail here, not filter to nothing downstream."""

    with pytest.raises(ValidationError):
        InventoryRiskQuery(risk_level="catastrophic")


def test_the_expiry_agents_risk_levels_are_rejected():
    """A real confusion risk: two agents, two enums. 'expired' and 'low' belong to
    expiry and mean nothing here."""

    for wrong in ("expired", "low"):
        with pytest.raises(ValidationError):
            InventoryRiskQuery(risk_level=wrong)


# ---------------------------------------------------------------------------
# min_capital_at_risk
# ---------------------------------------------------------------------------


def test_a_capital_floor_is_accepted():
    assert InventoryRiskQuery(min_capital_at_risk=25_000).min_capital_at_risk == 25_000


def test_zero_is_accepted_as_no_floor():
    assert InventoryRiskQuery(min_capital_at_risk=0).min_capital_at_risk == 0.0


def test_a_negative_capital_floor_is_rejected():
    with pytest.raises(ValidationError):
        InventoryRiskQuery(min_capital_at_risk=-1)


# ---------------------------------------------------------------------------
# medicine_id
# ---------------------------------------------------------------------------


def test_a_medicine_id_is_accepted():
    assert InventoryRiskQuery(medicine_id=17).medicine_id == 17


def test_a_zero_medicine_id_is_rejected():
    """Ids start at 1. Zero is what an uncertain model produces when it has no id."""

    with pytest.raises(ValidationError):
        InventoryRiskQuery(medicine_id=0)


def test_a_negative_medicine_id_is_rejected():
    with pytest.raises(ValidationError):
        InventoryRiskQuery(medicine_id=-5)


# ---------------------------------------------------------------------------
# sort
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("option", [s.value for s in InventorySort])
def test_every_declared_sort_is_accepted(option):
    assert InventoryRiskQuery(sort=option).sort.value == option


def test_an_unknown_sort_is_rejected():
    with pytest.raises(ValidationError):
        InventoryRiskQuery(sort="cheapest_first")


def test_a_sort_cannot_smuggle_a_column_name():
    """The whole point of a closed enum here: sort must never become SQL."""

    for attempt in ("medicines.name", "cost_price DESC", "1; DROP TABLE batches"):
        with pytest.raises(ValidationError):
            InventoryRiskQuery(sort=attempt)


# ---------------------------------------------------------------------------
# limit
# ---------------------------------------------------------------------------


def test_limit_accepts_its_bounds():
    assert InventoryRiskQuery(limit=1).limit == 1
    assert InventoryRiskQuery(limit=MAX_LIMIT).limit == MAX_LIMIT


def test_a_zero_limit_is_rejected():
    with pytest.raises(ValidationError):
        InventoryRiskQuery(limit=0)


def test_a_negative_limit_is_rejected():
    with pytest.raises(ValidationError):
        InventoryRiskQuery(limit=-10)


def test_an_unbounded_limit_is_rejected():
    """A report is for a person to read, not a data export. Without a ceiling the
    model could ask for the whole catalogue in one response."""

    with pytest.raises(ValidationError):
        InventoryRiskQuery(limit=100_000)


# ---------------------------------------------------------------------------
# Unknown fields
# ---------------------------------------------------------------------------


def test_an_unknown_field_is_ignored_not_executed():
    """Pydantic's default is to drop unknown keys. What matters is that an invented
    parameter cannot become a filter — it must have no effect at all."""

    query = InventoryRiskQuery(supplier_name="Acme", order_by="cost_price")

    assert not hasattr(query, "supplier_name")
    assert query.sort is InventorySort.RISK


# ---------------------------------------------------------------------------
# describe()
# ---------------------------------------------------------------------------


def test_describe_summarises_the_request():
    query = InventoryRiskQuery(
        target_cover_days=30,
        risk_level=InventoryRiskLevel.DEAD,
        min_capital_at_risk=5000,
        sort=InventorySort.CAPITAL,
        limit=5,
    )

    described = query.describe()

    assert "target=30d" in described
    assert "risk=dead" in described
    assert "Rs 5,000" in described
    assert "capital_at_risk" in described
    assert "top 5" in described


def test_describe_leaks_no_results():
    """It goes into logs. It must describe the shape of the request and nothing the
    request returned."""

    assert InventoryRiskQuery().describe() == "target=60d sorted by risk top 10"
