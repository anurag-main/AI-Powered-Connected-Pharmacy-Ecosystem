"""The deterministic expiry-risk calculation.

No LLM anywhere in this file. Every number the agent reports comes from here, so this
is where correctness actually lives — the graph above it is plumbing.

Expectations are hand-computed and documented in `tests/factories.py`.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.ai.schemas.expiry_query import ExpiryRiskQuery, RiskLevel
from app.repositories.expiry_repository import BatchStock, ExpiryRepository
from app.services.expiry_risk_service import (
    ExpiryRiskConfig,
    ExpiryRiskService,
    _priority_score,
    _recommendation,
)

pytestmark = pytest.mark.unit

CONFIG = ExpiryRiskConfig()


@pytest.fixture
def service(expiry_db) -> ExpiryRiskService:
    return ExpiryRiskService(ExpiryRepository(expiry_db), CONFIG)


@pytest.fixture
def empty_service(db_session) -> ExpiryRiskService:
    return ExpiryRiskService(ExpiryRepository(db_session), CONFIG)


def assess(service, as_of, **kwargs):
    return service.assess(ExpiryRiskQuery(**kwargs), as_of=as_of)


def by_batch(report) -> dict[str, object]:
    return {item.batch_number: item for item in report.items}


# ---------------------------------------------------------------------------
# Days to expiry
# ---------------------------------------------------------------------------


def test_days_to_expiry_is_counted_from_the_reference_date(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["P1"].days_to_expiry == 5
    assert items["P2"].days_to_expiry == 20
    assert items["V1"].days_to_expiry == 15


def test_an_expired_batch_reports_negative_days(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["C1"].days_to_expiry == -10


def test_a_batch_expiring_today_has_zero_days(db_session, expiry_as_of):
    """Zero days means it can still be sold today, but no demand accrues."""

    from tests.factories import seed_expiry_scenario
    from app.models.batch import Batch

    seed_expiry_scenario(db_session, expiry_as_of)
    batch = db_session.query(Batch).filter_by(batch_number="P1").one()
    batch.expiry_date = expiry_as_of
    db_session.commit()

    service = ExpiryRiskService(ExpiryRepository(db_session), CONFIG)
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["P1"].days_to_expiry == 0
    assert items["P1"].estimated_demand == 0, "no days left means no time to sell"
    assert items["P1"].risk_level is RiskLevel.CRITICAL


def test_a_batch_expiring_tomorrow(db_session, expiry_as_of):
    from tests.factories import seed_expiry_scenario
    from app.models.batch import Batch

    seed_expiry_scenario(db_session, expiry_as_of)
    batch = db_session.query(Batch).filter_by(batch_number="P1").one()
    batch.expiry_date = expiry_as_of + timedelta(days=1)
    db_session.commit()

    service = ExpiryRiskService(ExpiryRepository(db_session), CONFIG)
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["P1"].days_to_expiry == 1
    # One day at 2/day.
    assert items["P1"].estimated_demand == 2


# ---------------------------------------------------------------------------
# Demand, and the FEFO allocation that makes it per-batch
# ---------------------------------------------------------------------------


def test_demand_comes_from_real_sales(service, expiry_as_of):
    """Paracetamol sold 180 units over the 90-day lookback = 2/day.
    P1 expires in 5 days, so 5 x 2 = 10 units are expected to sell."""

    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["P1"].estimated_demand == 10


def test_a_later_batch_only_gets_the_demand_the_earlier_one_leaves(
    service, expiry_as_of
):
    """The FEFO point, and the reason this is not just an expiry report.

    Paracetamol sells 2/day. P2 expires in 20 days, so 40 units of demand exist by
    then — but P1 is ahead of it in the FEFO queue and takes 10. P2 therefore gets 30,
    not 40, and certainly not the 20 an even split across two batches would give it.
    """

    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["P1"].estimated_demand == 10
    assert items["P2"].estimated_demand == 30
    assert items["P1"].estimated_demand + items["P2"].estimated_demand == 40


def test_a_medicine_never_sold_gets_zero_demand(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["A1"].estimated_demand == 0
    assert items["A1"].potential_excess == 50


def test_no_sales_history_is_flagged_rather_than_treated_as_a_fact(
    service, expiry_as_of
):
    """Zero demand from no data means "unknown", not "will not sell". The report has
    to say which, or the analyst presents a guess as a finding."""

    report = assess(service, expiry_as_of, window_days=365, limit=100)

    assert any(
        "No sales history at all" in note and "Amoxicillin" in note
        for note in report.notes
    )


def test_sold_long_ago_but_not_recently_is_a_different_note(service, expiry_as_of):
    """Cough syrup sold 200 days ago, outside the 90-day lookback. It has history but
    no current demand — a slow mover, not an unknown."""

    report = assess(service, expiry_as_of, window_days=365, limit=100)

    assert any("nothing in the last 90 days" in note for note in report.notes)
    assert not any(
        "No sales history at all" in note and "Cough Syrup" in note
        for note in report.notes
    )


def test_expired_stock_does_not_consume_demand(service, expiry_as_of):
    """An expired batch cannot sell, so it must not eat demand a live batch needs."""

    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["C1"].estimated_demand == 0


# ---------------------------------------------------------------------------
# Excess
# ---------------------------------------------------------------------------


def test_stock_above_demand_produces_excess(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    # P1: 30 in stock, 10 expected to sell.
    assert items["P1"].potential_excess == 20
    # P2: 200 in stock, 30 expected to sell.
    assert items["P2"].potential_excess == 170


def test_stock_below_demand_produces_no_excess(service, expiry_as_of):
    """Vitamin C sells 10/day and has 40 units expiring in 15 days: 150 units of
    demand against 40 in stock. It clears comfortably.

    A report that flagged this batch because it "expires within 30 days" would be
    noise, and noise is what makes people stop reading the report.
    """

    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["V1"].potential_excess == 0
    assert items["V1"].risk_level is RiskLevel.LOW


def test_stock_exactly_equal_to_demand_is_not_excess(db_session, expiry_as_of):
    from tests.factories import seed_expiry_scenario
    from app.models.batch import Batch

    seed_expiry_scenario(db_session, expiry_as_of)
    # 5 days at 2/day = 10 units of demand; set stock to exactly that.
    batch = db_session.query(Batch).filter_by(batch_number="P1").one()
    batch.quantity = 10
    db_session.commit()

    service = ExpiryRiskService(ExpiryRepository(db_session), CONFIG)
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["P1"].estimated_demand == 10
    assert items["P1"].potential_excess == 0
    assert items["P1"].risk_level is RiskLevel.LOW


def test_expired_stock_is_all_excess(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["C1"].potential_excess == 25


# ---------------------------------------------------------------------------
# Value at risk
# ---------------------------------------------------------------------------


def test_value_at_risk_is_excess_times_unit_cost(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["P1"].value_at_risk == 200.00      # 20 x 10.00
    assert items["P2"].value_at_risk == 1700.00     # 170 x 10.00
    assert items["A1"].value_at_risk == 1000.00     # 50 x 20.00
    assert items["C1"].value_at_risk == 1000.00     # 25 x 40.00


def test_no_excess_means_no_value_at_risk(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["V1"].value_at_risk == 0.00


def test_a_zero_cost_batch_reports_zero_value_not_an_error(db_session, expiry_as_of):
    """Free samples exist. Zero cost is valid data, and the excess still matters even
    though the money does not."""

    from tests.factories import seed_expiry_scenario
    from app.models.batch import Batch

    seed_expiry_scenario(db_session, expiry_as_of)
    batch = db_session.query(Batch).filter_by(batch_number="A1").one()
    batch.cost_price = Decimal("0.00")
    db_session.commit()

    service = ExpiryRiskService(ExpiryRepository(db_session), CONFIG)
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["A1"].value_at_risk == 0.00
    assert items["A1"].potential_excess == 50, "the stock is still at risk"


def test_the_report_totals_only_count_batches_actually_at_risk(service, expiry_as_of):
    """Vitamin C is in the report but has no excess, so it must not inflate the total."""

    report = assess(service, expiry_as_of, window_days=365, limit=100)

    # C1 1000 + P2 1700 + A1 1000 + P1 200 + Z1 100 = 4000.
    # Z1 is 300 days out and only LOW risk, but it is never-sold stock with 100 units
    # and so genuinely has excess — low urgency is not the same as no exposure.
    # V1 is the only batch contributing nothing, because its demand clears it.
    assert report.total_value_at_risk == 4000.00
    assert report.total_at_risk == 5
    assert report.total_batches_reviewed == 6


# ---------------------------------------------------------------------------
# Risk levels
# ---------------------------------------------------------------------------


def test_already_expired_is_expired(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["C1"].risk_level is RiskLevel.EXPIRED


def test_excess_within_the_critical_window_is_critical(service, expiry_as_of):
    """P1: 5 days left, 20 units of excess."""

    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["P1"].risk_level is RiskLevel.CRITICAL


def test_excess_within_the_warning_window_is_high(service, expiry_as_of):
    """P2: 20 days left, 170 units of excess."""

    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["P2"].risk_level is RiskLevel.HIGH
    assert items["A1"].risk_level is RiskLevel.HIGH


def test_excess_beyond_the_warning_window_is_medium(db_session, expiry_as_of):
    from tests.factories import seed_expiry_scenario
    from app.models.batch import Batch

    seed_expiry_scenario(db_session, expiry_as_of)
    batch = db_session.query(Batch).filter_by(batch_number="A1").one()
    batch.expiry_date = expiry_as_of + timedelta(days=60)
    db_session.commit()

    service = ExpiryRiskService(ExpiryRepository(db_session), CONFIG)
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["A1"].risk_level is RiskLevel.MEDIUM


def test_no_excess_is_low_however_close_the_expiry(service, expiry_as_of):
    """Excess gates the whole classification. A batch expiring tomorrow that sells out
    tomorrow is not a risk, and calling it one trains people to ignore the report."""

    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["V1"].days_to_expiry == 15
    assert items["V1"].risk_level is RiskLevel.LOW


def test_stock_beyond_the_horizon_is_low(service, expiry_as_of):
    """Z1 expires in 300 days. It has excess, but not urgently."""

    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["Z1"].risk_level is RiskLevel.LOW


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (0, RiskLevel.CRITICAL),
        (7, RiskLevel.CRITICAL),    # boundary: critical_days inclusive
        (8, RiskLevel.HIGH),
        (30, RiskLevel.HIGH),       # boundary: warning_days inclusive
        (31, RiskLevel.MEDIUM),
        (90, RiskLevel.MEDIUM),     # boundary: horizon_days inclusive
        (91, RiskLevel.LOW),
    ],
)
def test_risk_level_boundaries_are_inclusive(days, expected):
    """Off-by-one at a threshold silently reclassifies a whole band of stock."""

    service = ExpiryRiskService(repository=None, config=CONFIG)  # type: ignore[arg-type]

    assert service._risk_level(days, excess=10) is expected


def test_every_item_explains_its_level(service, expiry_as_of):
    """An unexplained risk score is one nobody trusts or acts on."""

    report = assess(service, expiry_as_of, window_days=365, limit=100)

    for item in report.items:
        assert item.reasons, item.batch_number
        assert any("day(s)" in reason for reason in item.reasons)


def test_the_reasons_carry_the_actual_numbers(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))
    reasons = " ".join(items["P2"].reasons)

    assert "20 day(s) to expiry" in reasons
    assert "200 unit(s) in stock" in reasons
    assert "170 unit(s)" in reasons


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_expired_stock_ranks_first(service, expiry_as_of):
    """Realised loss outranks predicted loss."""

    report = assess(service, expiry_as_of, window_days=365, limit=100)

    assert report.items[0].batch_number == "C1"


def test_severity_outranks_value(service, expiry_as_of):
    """Risk level is the primary sort key, and deliberately so.

    P1 risks only 200 but expires in 5 days; P2 risks 1700 and has 20 days. P2 is the
    bigger number, but P1 is the one you can still do something about this week — so
    CRITICAL sorts above HIGH regardless of value. Sorting purely by money would bury
    the item with a closing window.
    """

    report = assess(service, expiry_as_of, window_days=365, limit=100)
    order = [item.batch_number for item in report.items]

    assert order.index("P1") < order.index("P2")


def test_value_per_day_breaks_ties_within_a_risk_level(service, expiry_as_of):
    """Within one severity band, the score decides: money at risk per day left.

    A1 risks 1000 over 10 days (100/day); P2 risks 1700 over 20 days (85/day). Both
    are HIGH, so the faster bleed goes first even though its total is smaller.
    """

    report = assess(service, expiry_as_of, window_days=365, limit=100)
    items = by_batch(report)
    order = [item.batch_number for item in report.items]

    assert items["A1"].risk_level is items["P2"].risk_level
    assert items["A1"].priority_score == 100.00
    assert items["P2"].priority_score == 85.00
    assert order.index("A1") < order.index("P2")


def test_the_priority_score_is_value_per_remaining_day(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert items["P1"].priority_score == 40.00      # 200 over 5 days
    assert items["P2"].priority_score == 85.00      # 1700 over 20 days


def test_batches_with_no_risk_rank_last(service, expiry_as_of):
    report = assess(service, expiry_as_of, window_days=365, limit=100)
    order = [item.batch_number for item in report.items]

    assert order.index("V1") > order.index("A1")


def test_ranking_is_stable_across_runs(service, expiry_as_of):
    """Two identical runs must produce the same order. A ranking that flaps looks
    broken even when the numbers are right."""

    first = [i.batch_number for i in assess(service, expiry_as_of, window_days=365, limit=100).items]
    second = [i.batch_number for i in assess(service, expiry_as_of, window_days=365, limit=100).items]

    assert first == second


def test_identical_batches_are_ordered_deterministically(db_session, expiry_as_of):
    """Same medicine, same expiry, same cost — only the id separates them."""

    from tests.factories import seed_expiry_scenario
    from app.models.batch import Batch
    from app.models.medicine import Medicine

    seed_expiry_scenario(db_session, expiry_as_of)
    amox = db_session.query(Medicine).filter_by(name="Amoxicillin 250").one()
    twin = Batch(
        medicine_id=amox.id,
        batch_number="A2",
        expiry_date=expiry_as_of + timedelta(days=10),
        quantity=50,
        cost_price=Decimal("20.00"),
    )
    db_session.add(twin)
    db_session.commit()

    service = ExpiryRiskService(ExpiryRepository(db_session), CONFIG)
    order = [
        i.batch_number
        for i in assess(service, expiry_as_of, window_days=365, limit=100).items
        if i.batch_number.startswith("A")
    ]

    assert order == ["A1", "A2"], "lower batch id first, every time"


def test_priority_score_never_divides_by_zero():
    """Expired stock has days <= 0 and must score its full value, not crash."""

    assert _priority_score(1000.0, 0) == 1000.0
    assert _priority_score(1000.0, -10) == 1000.0
    assert _priority_score(0.0, 30) == 0.0


# ---------------------------------------------------------------------------
# Query parameters
# ---------------------------------------------------------------------------


def test_the_window_excludes_stock_expiring_later(service, expiry_as_of):
    report = assess(service, expiry_as_of, window_days=30, limit=100)

    assert "Z1" not in by_batch(report)


def test_a_short_window_keeps_only_the_soonest(service, expiry_as_of):
    report = assess(service, expiry_as_of, window_days=7, limit=100)
    batches = set(by_batch(report))

    assert batches == {"P1", "C1"}, "P1 expires in 5 days; C1 already expired"


def test_expired_stock_can_be_excluded(service, expiry_as_of):
    report = assess(service, expiry_as_of, window_days=365, include_expired=False, limit=100)

    assert "C1" not in by_batch(report)


def test_filtering_by_risk_level(service, expiry_as_of):
    report = assess(service, expiry_as_of, window_days=365, risk_level="critical", limit=100)

    assert set(by_batch(report)) == {"P1"}


def test_filtering_by_medicine(service, expiry_as_of, expiry_db):
    from app.models.medicine import Medicine

    paracetamol = expiry_db.query(Medicine).filter_by(name="Paracetamol 500").one()
    report = assess(
        service, expiry_as_of, window_days=365, medicine_id=paracetamol.id, limit=100
    )

    assert set(by_batch(report)) == {"P1", "P2"}


def test_the_limit_keeps_the_highest_priority_items(service, expiry_as_of):
    """Ranking must happen before the limit, or "top 2" means "first 2 from SQL"."""

    report = assess(service, expiry_as_of, window_days=365, limit=2)

    # C1 is expired, P1 is the only critical one. Both outrank the larger HIGH losses.
    assert [item.batch_number for item in report.items] == ["C1", "P1"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_an_empty_database_returns_an_empty_report(empty_service, expiry_as_of):
    report = assess(empty_service, expiry_as_of, window_days=90)

    assert report.items == []
    assert report.total_at_risk == 0
    assert report.total_value_at_risk == 0.0
    assert report.notes == ["No batches expire within the requested window."]


def test_a_window_with_nothing_in_it_returns_an_empty_report(db_session, expiry_as_of):
    """Distinct from an error: the query worked and found nothing."""

    from tests.factories import seed_expiry_scenario

    seed_expiry_scenario(db_session, expiry_as_of)
    service = ExpiryRiskService(ExpiryRepository(db_session), CONFIG)

    report = assess(service, expiry_as_of, window_days=1, include_expired=False)

    assert report.items == []


def test_zero_quantity_batches_are_ignored(db_session, expiry_as_of):
    """Nothing on the shelf, nothing at risk."""

    from tests.factories import seed_expiry_scenario
    from app.models.batch import Batch

    seed_expiry_scenario(db_session, expiry_as_of)
    batch = db_session.query(Batch).filter_by(batch_number="A1").one()
    batch.quantity = 0
    db_session.commit()

    service = ExpiryRiskService(ExpiryRepository(db_session), CONFIG)

    assert "A1" not in by_batch(assess(service, expiry_as_of, window_days=365, limit=100))


def test_negative_stock_is_surfaced_not_hidden(db_session, expiry_as_of):
    """`batches.quantity` has no CHECK constraint, so negative values are reachable.

    Treated as nothing at risk — a negative write-off would be nonsense — but reported
    loudly, because it is a data bug someone needs to fix.
    """

    from tests.factories import seed_expiry_scenario
    from app.models.batch import Batch

    seed_expiry_scenario(db_session, expiry_as_of)
    batch = db_session.query(Batch).filter_by(batch_number="A1").one()
    batch.quantity = -5
    db_session.commit()

    service = ExpiryRiskService(ExpiryRepository(db_session), CONFIG)
    report = assess(service, expiry_as_of, window_days=365, limit=100)
    item = by_batch(report)["A1"]

    assert item.stock_quantity == -5, "the real value is reported, not scrubbed"
    assert item.potential_excess == 0
    assert item.value_at_risk == 0.0
    assert any("should not be possible" in reason for reason in item.reasons)
    assert any("Negative stock" in note for note in report.notes)


def test_very_large_stock_is_handled(db_session, expiry_as_of):
    from tests.factories import seed_expiry_scenario
    from app.models.batch import Batch

    seed_expiry_scenario(db_session, expiry_as_of)
    batch = db_session.query(Batch).filter_by(batch_number="P2").one()
    batch.quantity = 1_000_000
    db_session.commit()

    service = ExpiryRiskService(ExpiryRepository(db_session), CONFIG)
    item = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))["P2"]

    assert item.potential_excess == 999_970
    assert item.value_at_risk == 9_999_700.00


def test_the_estimate_is_always_labelled_as_an_estimate(service, expiry_as_of):
    """The report must never let itself be read as a forecast."""

    report = assess(service, expiry_as_of, window_days=90)

    assert any("not a forecast" in note for note in report.notes)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


def test_every_item_carries_a_recommendation(service, expiry_as_of):
    report = assess(service, expiry_as_of, window_days=365, limit=100)

    assert all(item.recommendation for item in report.items)


def test_a_healthy_batch_is_told_to_do_nothing(service, expiry_as_of):
    items = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))

    assert "No action needed" in items["V1"].recommendation


def test_recommendations_never_promise_an_action(service, expiry_as_of):
    """The agent advises. It does not discount, order, email or move anything.

    Wording matters: "consider a discount" is advice, "applying a discount" would
    imply the system did something it cannot do.
    """

    report = assess(service, expiry_as_of, window_days=365, limit=100)
    forbidden = ("i have ", "i've ", "applied", "ordered", "emailed", "transferred")

    for item in report.items:
        lowered = item.recommendation.lower()
        assert not any(word in lowered for word in forbidden), item.recommendation


def test_expired_stock_is_told_to_write_off_and_investigate():
    text = _recommendation(RiskLevel.EXPIRED, excess=25, days=-10)

    assert "write off" in text.lower()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_the_defaults_are_sane():
    config = ExpiryRiskConfig()

    assert config.critical_days < config.warning_days <= config.horizon_days


def test_thresholds_can_be_overridden(monkeypatch):
    monkeypatch.setenv("EXPIRY_CRITICAL_DAYS", "3")
    monkeypatch.setenv("EXPIRY_WARNING_DAYS", "14")

    config = ExpiryRiskConfig.from_env()

    assert config.critical_days == 3
    assert config.warning_days == 14


def test_overlapping_thresholds_are_rejected(monkeypatch):
    """critical >= warning makes the HIGH band unreachable, so the report would
    silently never classify anything as high."""

    monkeypatch.setenv("EXPIRY_CRITICAL_DAYS", "40")
    monkeypatch.setenv("EXPIRY_WARNING_DAYS", "30")

    with pytest.raises(RuntimeError, match="critical < warning"):
        ExpiryRiskConfig.from_env()


@pytest.mark.parametrize("value", ["nonsense", "0", "-5"])
def test_an_invalid_threshold_fails_loudly(monkeypatch, value):
    monkeypatch.setenv("EXPIRY_CRITICAL_DAYS", value)

    with pytest.raises(RuntimeError, match="EXPIRY_CRITICAL_DAYS"):
        ExpiryRiskConfig.from_env()


def test_a_shorter_lookback_changes_the_demand_estimate(expiry_db, expiry_as_of):
    """The lookback is a real business choice, not a constant.

    Paracetamol's 180 units all landed 30 days ago. Over 90 days that averages 2/day;
    over 45 it averages 4/day, and the risk drops accordingly.
    """

    config = ExpiryRiskConfig(demand_lookback_days=45)
    service = ExpiryRiskService(ExpiryRepository(expiry_db), config)

    item = by_batch(assess(service, expiry_as_of, window_days=365, limit=100))["P1"]

    assert item.estimated_demand == 20, "5 days at 4/day"
    assert item.potential_excess == 10


def test_the_report_states_the_lookback_it_used(service, expiry_as_of):
    report = assess(service, expiry_as_of, window_days=90)

    assert report.demand_lookback_days == CONFIG.demand_lookback_days
