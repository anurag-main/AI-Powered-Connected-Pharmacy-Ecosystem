"""InventoryRiskService — the deterministic capital calculation.

Every number here is checkable by hand, and every test states the arithmetic it
expects rather than asserting that some value is "reasonable". That is the whole
argument for computing this in Python instead of asking a model: if a pharmacist
disputes a figure, there is a line of code to point at.

The fixtures build one fact at a time. A shared scenario would make a failure point
at the fixture rather than at the rule that broke.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.supplier import Supplier
from app.repositories.inventory_repository import InventoryRepository
from app.services.demand_service import DemandService
from app.services.inventory_risk_service import (
    InventoryRiskConfig,
    InventoryRiskLevel,
    InventoryRiskService,
)

pytestmark = pytest.mark.unit


AS_OF = date(2026, 6, 30)

#: Pinned so a threshold change in the defaults cannot silently rewrite these tests.
CONFIG = InventoryRiskConfig(
    target_cover_days=60,
    overstock_cover_days=120,
    high_cover_days=180,
    critical_cover_days=365,
    dead_stock_days=180,
    medium_value=2_000.0,
    high_value=10_000.0,
    critical_value=25_000.0,
    demand_lookback_days=90,
)


@pytest.fixture
def build(db_session):
    """Stock a medicine, sell some of it, record when it arrived."""

    supplier = Supplier(name="Acme Distributors", phone="9000000000")
    db_session.add(supplier)
    db_session.flush()

    class Builder:
        def stock(
            self,
            name: str,
            *,
            units: int,
            cost: str,
            expires_in_days: int = 365,
            received_days_ago: int | None = None,
        ) -> Medicine:
            medicine = Medicine(
                name=name,
                normalized_name=name.lower(),
                mrp=Decimal("50.00"),
                hsn_code="30049099",
                manufacturer="Generic Pharma",
            )
            db_session.add(medicine)
            db_session.flush()
            self.add_batch(
                medicine,
                units=units,
                cost=cost,
                expires_in_days=expires_in_days,
                received_days_ago=received_days_ago,
            )
            return medicine

        def add_batch(
            self,
            medicine: Medicine,
            *,
            units: int,
            cost: str,
            expires_in_days: int = 365,
            received_days_ago: int | None = None,
        ) -> Batch:
            batch = Batch(
                medicine_id=medicine.id,
                batch_number=f"B{medicine.id}-{units}-{expires_in_days}",
                expiry_date=AS_OF + timedelta(days=expires_in_days),
                quantity=units,
                cost_price=Decimal(cost),
            )
            db_session.add(batch)
            db_session.flush()

            if received_days_ago is not None:
                purchase = Purchase(
                    supplier_id=supplier.id,
                    purchase_date=AS_OF - timedelta(days=received_days_ago),
                    invoice_number=f"INV-{batch.id}",
                    total_amount=Decimal("100.00"),
                )
                db_session.add(purchase)
                db_session.flush()
                db_session.add(
                    PurchaseItem(
                        purchase_id=purchase.id,
                        medicine_id=medicine.id,
                        batch_id=batch.id,
                        quantity=max(units, 1),
                        unit_cost=batch.cost_price,
                        line_total=batch.cost_price * max(units, 1),
                    )
                )
                db_session.flush()

            return batch

        def sell(self, medicine: Medicine, *, units: int, days_ago: int) -> None:
            batch = (
                db_session.query(Batch).filter_by(medicine_id=medicine.id).first()
            )
            sale = Sale(
                customer_id=None,
                total_amount=Decimal(units) * medicine.mrp,
                sold_at=datetime.combine(AS_OF - timedelta(days=days_ago), time(12, 0)),
            )
            db_session.add(sale)
            db_session.flush()
            db_session.add(
                SaleItem(
                    sale_id=sale.id,
                    medicine_id=medicine.id,
                    batch_id=batch.id,
                    quantity=units,
                    unit_price=medicine.mrp,
                    line_total=Decimal(units) * medicine.mrp,
                )
            )
            db_session.flush()

    return Builder()


@pytest.fixture
def service(db_session) -> InventoryRiskService:
    return InventoryRiskService(
        InventoryRepository(db_session), DemandService(db_session), CONFIG
    )


def assess(service, db_session):
    db_session.commit()
    return service.assess(as_of=AS_OF)


def only(report):
    assert len(report.items) == 1, f"expected one item, got {len(report.items)}"
    return report.items[0]


# ---------------------------------------------------------------------------
# Inventory value
# ---------------------------------------------------------------------------


def test_inventory_value_is_quantity_times_cost(service, build, db_session):
    build.stock("Paracetamol 500", units=100, cost="20.00")

    assert only(assess(service, db_session)).inventory_value == 2000.00


def test_the_unit_cost_is_weighted_across_batches(service, build, db_session):
    """100 at Rs 20 and 100 at Rs 40 is Rs 30 a unit, not Rs 20 and not Rs 40.
    Valuing the excess at either batch's price would misstate the capital."""

    medicine = build.stock("Paracetamol 500", units=100, cost="20.00")
    build.add_batch(medicine, units=100, cost="40.00")

    item = only(assess(service, db_session))

    assert item.inventory_value == 6000.00
    assert item.weighted_avg_cost == 30.0


def test_zero_cost_stock_is_worth_nothing_but_still_appears(service, build, db_session):
    build.stock("Sample Sachet", units=500, cost="0.00")

    item = only(assess(service, db_session))

    assert item.inventory_value == 0.0
    assert item.stock_quantity == 500


# ---------------------------------------------------------------------------
# Velocity and days of cover
# ---------------------------------------------------------------------------


def test_velocity_comes_from_the_shared_lookback(service, build, db_session):
    """900 units across the 90-day window is 10 a day."""

    medicine = build.stock("Paracetamol 500", units=100, cost="20.00")
    build.sell(medicine, units=900, days_ago=30)

    item = only(assess(service, db_session))

    assert item.units_sold == 900
    assert item.daily_velocity == 10.0


def test_days_of_cover_is_sellable_stock_over_velocity(service, build, db_session):
    medicine = build.stock("Paracetamol 500", units=100, cost="20.00")
    build.sell(medicine, units=900, days_ago=30)

    assert only(assess(service, db_session)).days_of_cover == 10.0


def test_cover_uses_sellable_stock_not_total_stock(service, build, db_session):
    """Expired units cannot satisfy a day of demand. Counting them would make a shelf
    of dead product look well supplied."""

    medicine = build.stock("Ibuprofen 400", units=60, cost="10.00", expires_in_days=200)
    build.add_batch(medicine, units=40, cost="10.00", expires_in_days=-5)
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.stock_quantity == 100
    assert item.sellable_quantity == 60
    assert item.days_of_cover == 60.0, "60 sellable at 1/day, not 100"


def test_cover_is_none_when_nothing_is_selling(service, build, db_session):
    """Not infinity. ``inf`` compares greater than every cover threshold, so a
    never-sold medicine would be classified as overstock by the cover rule — a claim
    about a rate that was never measured. ``None`` forces the dead-stock rule."""

    build.stock("Amoxicillin 250", units=500, cost="50.00")

    item = only(assess(service, db_session))

    assert item.daily_velocity == 0.0
    assert item.days_of_cover is None


def test_a_sale_outside_the_lookback_does_not_create_velocity(
    service, build, db_session
):
    medicine = build.stock("Cough Syrup 100ml", units=60, cost="40.00")
    build.sell(medicine, units=50, days_ago=200)

    item = only(assess(service, db_session))

    assert item.units_sold == 0
    assert item.days_of_cover is None
    assert item.ever_sold is True, "it has history, just not recent history"


# ---------------------------------------------------------------------------
# Target, excess and capital at risk
# ---------------------------------------------------------------------------


def test_target_stock_is_the_target_cover_at_current_velocity(
    service, build, db_session
):
    """1 a day over a 60-day target is 60 units."""

    medicine = build.stock("Cetirizine 10", units=400, cost="100.00")
    build.sell(medicine, units=90, days_ago=30)

    assert only(assess(service, db_session)).target_stock == 60


def test_target_stock_rounds_up(service, build, db_session):
    """0.5/day over 60 days is 30.0; 90 units over 90 days with an odd figure must not
    round a partial unit down and understate what the shop should hold."""

    medicine = build.stock("Cetirizine 10", units=400, cost="100.00")
    build.sell(medicine, units=100, days_ago=30)

    item = only(assess(service, db_session))

    assert item.daily_velocity == pytest.approx(100 / 90)
    assert item.target_stock == 67, "ceil(1.111... * 60)"


def test_excess_is_stock_above_the_target(service, build, db_session):
    medicine = build.stock("Cetirizine 10", units=400, cost="100.00")
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.excess_units == 340, "400 sellable minus a 60-unit target"
    assert item.excess_value == 34_000.00


def test_stock_below_the_target_has_no_excess(service, build, db_session):
    """A fast mover holding ten days of stock is not overstocked; it is under-stocked,
    which is the reorder agent's problem, not this one's."""

    medicine = build.stock("Paracetamol 500", units=100, cost="20.00")
    build.sell(medicine, units=900, days_ago=30)

    item = only(assess(service, db_session))

    assert item.excess_units == 0
    assert item.excess_value == 0.0


def test_capital_at_risk_is_the_excess_not_the_whole_shelf(service, build, db_session):
    """A shop must hold stock to trade. The target cover is capital doing its job."""

    medicine = build.stock("Cetirizine 10", units=400, cost="100.00")
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.inventory_value == 40_000.00
    assert item.capital_at_risk == 34_000.00


def test_dead_stock_puts_the_whole_value_at_risk(service, build, db_session):
    """Nothing is moving, so none of it is coming back through the till."""

    build.stock("Amoxicillin 250", units=500, cost="50.00")

    item = only(assess(service, db_session))

    assert item.risk_level is InventoryRiskLevel.DEAD
    assert item.capital_at_risk == 25_000.00 == item.inventory_value


def test_dead_stock_capital_includes_the_expired_part(service, build, db_session):
    """Unlike cover, capital does not care whether the units are sellable."""

    medicine = build.stock("Amoxicillin 250", units=300, cost="50.00")
    build.add_batch(medicine, units=200, cost="50.00", expires_in_days=-10)

    item = only(assess(service, db_session))

    assert item.sellable_quantity == 300
    assert item.capital_at_risk == 25_000.00, "all 500 units, expired or not"


# ---------------------------------------------------------------------------
# Dead stock — the three distinct states
# ---------------------------------------------------------------------------


def test_never_sold_is_dead_stock(service, build, db_session):
    build.stock("Amoxicillin 250", units=500, cost="50.00")

    item = only(assess(service, db_session))

    assert item.risk_level is InventoryRiskLevel.DEAD
    assert item.ever_sold is False
    assert item.last_sale_date is None
    assert item.days_since_last_sale is None
    assert "never sold" in item.risk_reasons


def test_sold_long_ago_is_dead_stock_but_a_different_reason(service, build, db_session):
    """A slow mover and a product that never launched need different advice, so the
    two are not collapsed into one state."""

    medicine = build.stock("Cough Syrup 100ml", units=60, cost="40.00")
    build.sell(medicine, units=50, days_ago=200)

    item = only(assess(service, db_session))

    assert item.risk_level is InventoryRiskLevel.DEAD
    assert item.ever_sold is True
    assert item.last_sale_date == AS_OF - timedelta(days=200)
    assert item.days_since_last_sale == 200
    assert "last sold 200 day(s) ago" in item.risk_reasons


def test_a_medicine_with_no_stock_is_not_dead_stock_it_is_absent(
    service, build, db_session
):
    """Zero inventory is a third state. No capital is tied up, so there is nothing at
    risk — but the report says how many were left out rather than dropping them."""

    build.stock("Domperidone 10", units=0, cost="15.00")

    report = assess(service, db_session)

    assert report.items == []
    assert report.medicines_without_stock == 1


def test_dead_stock_boundary_is_inclusive(service, build, db_session):
    """Exactly 180 days since the last sale is dead."""

    medicine = build.stock("Cough Syrup 100ml", units=60, cost="40.00")
    build.sell(medicine, units=50, days_ago=180)

    assert only(assess(service, db_session)).risk_level is InventoryRiskLevel.DEAD


def test_one_day_inside_the_dead_stock_boundary_is_not_dead(service, build, db_session):
    medicine = build.stock("Cough Syrup 100ml", units=60, cost="40.00")
    build.sell(medicine, units=50, days_ago=179)

    assert only(assess(service, db_session)).risk_level is not InventoryRiskLevel.DEAD


# ---------------------------------------------------------------------------
# Risk classification — the thresholds
# ---------------------------------------------------------------------------


def test_stock_inside_the_target_is_healthy(service, build, db_session):
    medicine = build.stock("Paracetamol 500", units=100, cost="20.00")
    build.sell(medicine, units=900, days_ago=30)

    item = only(assess(service, db_session))

    assert item.risk_level is InventoryRiskLevel.HEALTHY
    assert "within the target cover" in item.risk_reasons


def test_cover_just_past_the_overstock_threshold_is_medium(service, build, db_session):
    """121 days of cover on cheap stock: over the line by cover, under it by money."""

    medicine = build.stock("Vitamin C 500", units=121, cost="1.00")
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.days_of_cover == 121.0
    assert item.excess_value == 61.0, "below every rupee gate"
    assert item.risk_level is InventoryRiskLevel.MEDIUM


def test_cover_exactly_at_the_overstock_threshold_is_healthy(
    service, build, db_session
):
    """The rule is ``cover > 120``, so 120 itself is still acceptable."""

    medicine = build.stock("Vitamin C 500", units=120, cost="1.00")
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.days_of_cover == 120.0
    assert item.risk_level is InventoryRiskLevel.HEALTHY


def test_cover_past_the_high_threshold_is_high(service, build, db_session):
    medicine = build.stock("Vitamin C 500", units=181, cost="1.00")
    build.sell(medicine, units=90, days_ago=30)

    assert only(assess(service, db_session)).risk_level is InventoryRiskLevel.HIGH


def test_cover_past_a_year_is_critical(service, build, db_session):
    medicine = build.stock("Vitamin C 500", units=366, cost="1.00")
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.days_of_cover == 366.0
    assert item.risk_level is InventoryRiskLevel.CRITICAL


def test_money_alone_can_raise_the_level(service, build, db_session):
    """70 days of cover is nearly fine. Rs 26,000 trapped in it is not, and cover
    alone would have called this healthy."""

    medicine = build.stock("Expensive Injectable", units=70, cost="2600.00")
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.days_of_cover == 70.0
    assert item.excess_value == 26_000.00
    assert item.risk_level is InventoryRiskLevel.CRITICAL


def test_the_rupee_gate_is_inclusive(service, build, db_session):
    """Exactly Rs 25,000 of trapped capital is critical."""

    medicine = build.stock("Expensive Injectable", units=70, cost="2500.00")
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.excess_value == 25_000.00
    assert item.risk_level is InventoryRiskLevel.CRITICAL


def test_one_rupee_below_the_gate_drops_a_level(service, build, db_session):
    medicine = build.stock("Expensive Injectable", units=70, cost="2499.90")
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.excess_value == 24_999.00
    assert item.risk_level is InventoryRiskLevel.HIGH


def test_cheap_stock_with_huge_cover_still_surfaces(service, build, db_session):
    """Capital alone would miss a large pile of cheap stock that will never move."""

    medicine = build.stock("Bandage Roll", units=5_000, cost="0.50")
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.excess_value == 2_470.00
    assert item.days_of_cover == 5_000.0
    assert item.risk_level is InventoryRiskLevel.CRITICAL


# ---------------------------------------------------------------------------
# Stock age
# ---------------------------------------------------------------------------


def test_stock_age_comes_from_the_purchase_date(service, build, db_session):
    build.stock("Paracetamol 500", units=100, cost="20.00", received_days_ago=45)

    item = only(assess(service, db_session))

    assert item.oldest_receipt_date == AS_OF - timedelta(days=45)
    assert item.stock_age_days == 45


def test_stock_age_is_none_when_there_is_no_purchase_record(
    service, build, db_session
):
    """Never zero. Zero would say "arrived today", which is a claim, not an absence."""

    build.stock("Paracetamol 500", units=100, cost="20.00")

    item = only(assess(service, db_session))

    assert item.stock_age_days is None
    assert item.oldest_receipt_date is None


def test_unknown_stock_age_is_reported_in_the_notes(service, build, db_session):
    build.stock("Paracetamol 500", units=100, cost="20.00")

    report = assess(service, db_session)

    assert any("stock age is unknown" in note for note in report.notes)


def test_stock_age_tracks_the_oldest_batch_still_holding_stock(
    service, build, db_session
):
    medicine = build.stock(
        "Paracetamol 500", units=100, cost="20.00", received_days_ago=200
    )
    build.add_batch(medicine, units=50, cost="20.00", received_days_ago=10)

    assert only(assess(service, db_session)).stock_age_days == 200


# ---------------------------------------------------------------------------
# Reasons — the defence of the classification
# ---------------------------------------------------------------------------


def test_every_reason_is_checkable_against_the_item(service, build, db_session):
    medicine = build.stock(
        "Cetirizine 10", units=400, cost="100.00", received_days_ago=120
    )
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert "400 unit(s) in stock" in item.risk_reasons
    assert "selling 1.00 unit(s)/day" in item.risk_reasons
    assert "400 day(s) of cover" in item.risk_reasons
    assert "last sold 30 day(s) ago" in item.risk_reasons
    assert "oldest stock received 120 day(s) ago" in item.risk_reasons
    assert any("340 unit(s) above a 60-day target" in r for r in item.risk_reasons)


def test_the_reasons_never_mention_an_expiry_date(service, build, db_session):
    """The boundary with the expiry agent. Unsellable stock is stated as a count, so
    the two reports stay distinct rather than becoming the same screen twice."""

    medicine = build.stock("Ibuprofen 400", units=60, cost="10.00", expires_in_days=200)
    build.add_batch(medicine, units=40, cost="10.00", expires_in_days=-5)
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert "40 unit(s) no longer sellable" in item.risk_reasons
    assert not any("expir" in reason.lower() for reason in item.risk_reasons)
    assert not any(str(AS_OF.year) in reason for reason in item.risk_reasons)


def test_a_medicine_with_no_recent_sales_says_so(service, build, db_session):
    build.stock("Amoxicillin 250", units=500, cost="50.00")

    item = only(assess(service, db_session))

    assert "no sales in the last 90 day(s)" in item.risk_reasons


# ---------------------------------------------------------------------------
# A realistic pharmacy
# ---------------------------------------------------------------------------


@pytest.fixture
def pharmacy(build):
    """Six medicines covering every state the report can produce.

    | medicine     | stock | cost | sold          | expected                  |
    |--------------|-------|------|---------------|---------------------------|
    | Paracetamol  |   100 |   20 | 900 / 30d ago | healthy, 10 days cover    |
    | Amoxicillin  |   500 |   50 | never         | dead, Rs 25,000           |
    | Cetirizine   |   400 |  100 |  90 / 30d ago | critical, 400 days cover  |
    | Cough Syrup  |    60 |   40 |  50 / 200d ago| dead, inactive            |
    | Vitamin C    |   150 |   15 |  90 / 30d ago | medium, 150 days cover    |
    | Ibuprofen    | 60+40 |   10 |  90 / 30d ago | healthy, 40 unsellable    |
    | Domperidone  |     0 |   15 | never         | excluded, no capital      |
    """

    paracetamol = build.stock("Paracetamol 500", units=100, cost="20.00")
    build.sell(paracetamol, units=900, days_ago=30)

    build.stock("Amoxicillin 250", units=500, cost="50.00")

    cetirizine = build.stock("Cetirizine 10", units=400, cost="100.00")
    build.sell(cetirizine, units=90, days_ago=30)

    cough = build.stock("Cough Syrup 100ml", units=60, cost="40.00")
    build.sell(cough, units=50, days_ago=200)

    vitamin_c = build.stock("Vitamin C 500", units=150, cost="15.00")
    build.sell(vitamin_c, units=90, days_ago=30)

    ibuprofen = build.stock("Ibuprofen 400", units=60, cost="10.00", expires_in_days=200)
    build.add_batch(ibuprofen, units=40, cost="10.00", expires_in_days=-5)
    build.sell(ibuprofen, units=90, days_ago=30)

    build.stock("Domperidone 10", units=0, cost="15.00")

    return build


def test_the_whole_pharmacy_classifies_as_expected(service, pharmacy, db_session):
    report = assess(service, db_session)

    levels = {item.medicine_name: item.risk_level.value for item in report.items}

    assert levels == {
        "Paracetamol 500": "healthy",
        "Amoxicillin 250": "dead",
        "Cetirizine 10": "critical",
        "Cough Syrup 100ml": "dead",
        "Vitamin C 500": "medium",
        "Ibuprofen 400": "healthy",
    }


def test_the_worst_capital_comes_first(service, pharmacy, db_session):
    """Dead stock first, then by money. No computed priority score — an earlier design
    multiplied excess by a stock-age factor, which looks precise, cannot be checked by
    hand, and hides which input drove the ranking."""

    report = assess(service, db_session)

    assert [item.medicine_name for item in report.items] == [
        "Amoxicillin 250",   # dead, Rs 25,000
        "Cough Syrup 100ml", # dead, Rs 2,400
        "Cetirizine 10",     # critical, Rs 34,000
        "Vitamin C 500",     # medium, Rs 1,350
        "Paracetamol 500",   # healthy, Rs 2,000 of stock
        "Ibuprofen 400",     # healthy, Rs 1,000 of stock
    ]


def test_the_totals_add_up(service, pharmacy, db_session):
    report = assess(service, db_session)

    assert report.total_inventory_value == 72_650.00
    assert report.total_capital_at_risk == 62_750.00
    assert sum(item.inventory_value for item in report.items) == pytest.approx(72_650.00)


def test_capital_at_risk_is_less_than_inventory_value(service, pharmacy, db_session):
    """The gap is the stock doing its job. A report that called all of it "at risk"
    would be telling a pharmacist to stop trading."""

    report = assess(service, db_session)

    assert report.total_capital_at_risk < report.total_inventory_value


def test_the_counts_cover_every_level(service, pharmacy, db_session):
    report = assess(service, db_session)

    assert report.counts_by_risk == {
        "dead": 2,
        "critical": 1,
        "high": 0,
        "medium": 1,
        "healthy": 2,
    }
    assert sum(report.counts_by_risk.values()) == report.medicines_reviewed


def test_the_unstocked_medicine_is_counted_not_dropped(service, pharmacy, db_session):
    report = assess(service, db_session)

    assert report.medicines_reviewed == 6
    assert report.medicines_without_stock == 1


def test_the_report_states_what_it_measured(service, pharmacy, db_session):
    report = assess(service, db_session)

    assert report.generated_for == AS_OF
    assert report.demand_lookback_days == 90
    assert report.target_cover_days == 60
    assert any("not a forecast" in note for note in report.notes)


# ---------------------------------------------------------------------------
# Empty and degenerate cases
# ---------------------------------------------------------------------------


def test_an_empty_database_produces_an_empty_report(service, db_session):
    report = service.assess(as_of=AS_OF)

    assert report.items == []
    assert report.total_inventory_value == 0.0
    assert report.total_capital_at_risk == 0.0
    assert report.counts_by_risk == {
        "dead": 0, "critical": 0, "high": 0, "medium": 0, "healthy": 0
    }
    assert report.notes == ["No medicine currently holds stock."]


def test_a_catalogue_with_no_stock_at_all_still_counts_its_medicines(
    service, build, db_session
):
    build.stock("Domperidone 10", units=0, cost="15.00")
    build.stock("Ranitidine 150", units=0, cost="15.00")

    report = assess(service, db_session)

    assert report.medicines_reviewed == 0
    assert report.medicines_without_stock == 2


def test_a_negative_batch_is_reported_rather_than_hidden(service, build, db_session):
    medicine = build.stock("Paracetamol 500", units=100, cost="20.00")
    build.add_batch(medicine, units=-20, cost="20.00")
    build.sell(medicine, units=900, days_ago=30)

    report = assess(service, db_session)

    assert only(report).stock_quantity == 100
    assert any("negative quantity" in note for note in report.notes)


def test_very_large_inventory_does_not_break_the_arithmetic(service, build, db_session):
    medicine = build.stock("Bulk Saline", units=1_000_000, cost="12.50")
    build.sell(medicine, units=90, days_ago=30)

    item = only(assess(service, db_session))

    assert item.inventory_value == 12_500_000.00
    assert item.excess_units == 999_940
    assert item.risk_level is InventoryRiskLevel.CRITICAL


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_a_shorter_target_cover_creates_more_excess(db_session, build):
    """The target is a business dial, not a constant, and must visibly move the
    answer."""

    medicine = build.stock("Cetirizine 10", units=400, cost="100.00")
    build.sell(medicine, units=90, days_ago=30)
    db_session.commit()

    def excess(target_days: int) -> int:
        config = InventoryRiskConfig(
            target_cover_days=target_days,
            overstock_cover_days=120,
            high_cover_days=180,
            critical_cover_days=365,
            dead_stock_days=180,
            demand_lookback_days=90,
        )
        service = InventoryRiskService(
            InventoryRepository(db_session), DemandService(db_session), config
        )
        return service.assess(as_of=AS_OF).items[0].excess_units

    assert excess(60) == 340
    assert excess(30) == 370


def test_overlapping_cover_thresholds_are_rejected(monkeypatch):
    """An unreachable risk level would make the report silently misleading, so this
    fails at construction rather than at runtime."""

    monkeypatch.setenv("INVENTORY_HIGH_COVER_DAYS", "400")

    with pytest.raises(RuntimeError, match="cover thresholds"):
        InventoryRiskConfig.from_env()


def test_overlapping_value_thresholds_are_rejected(monkeypatch):
    monkeypatch.setenv("INVENTORY_MEDIUM_VALUE", "50000")

    with pytest.raises(RuntimeError, match="value thresholds"):
        InventoryRiskConfig.from_env()


def test_a_non_numeric_threshold_is_rejected(monkeypatch):
    monkeypatch.setenv("INVENTORY_TARGET_COVER_DAYS", "soon")

    with pytest.raises(RuntimeError, match="whole number"):
        InventoryRiskConfig.from_env()


def test_the_defaults_are_self_consistent():
    """The shipped configuration must satisfy its own validation."""

    assert InventoryRiskConfig.from_env() == InventoryRiskConfig()
