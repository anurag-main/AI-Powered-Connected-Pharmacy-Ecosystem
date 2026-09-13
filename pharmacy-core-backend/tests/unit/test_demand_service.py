"""DemandService — the one definition of how fast a medicine sells.

Three features now depend on these numbers, so the boundaries matter more than the
arithmetic. Most of this file is about *which sales count*, not about division.

The window is half-open, ``[start, end)``:

    start = midnight of (as_of - lookback_days)    INCLUDED
    end   = midnight of as_of                     EXCLUDED

so a sale at exactly ``start`` counts and a sale at exactly ``end`` does not. Both of
those are asserted below against a sale placed on the boundary to the second, because
an off-by-one here quietly changes every velocity in the system.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.services.demand_service import DemandService, DemandWindow, daily_velocity

pytestmark = pytest.mark.unit


AS_OF = date(2026, 6, 30)


@pytest.fixture
def service(db_session) -> DemandService:
    return DemandService(db_session)


@pytest.fixture
def medicines(db_session) -> dict[str, Medicine]:
    """Two medicines, so a sale for one can be shown not to leak into the other."""

    made = {}
    for name in ("Crocin 500", "Dolo 650"):
        medicine = Medicine(
            name=name,
            normalized_name=name.lower(),
            mrp=Decimal("15.00"),
            hsn_code="30049099",
            manufacturer="Generic Pharma",
        )
        db_session.add(medicine)
        made[name] = medicine
    db_session.flush()
    return made


@pytest.fixture
def sell(db_session, medicines):
    """Record a sale of ``units`` at an exact instant.

    The instant is the whole point of this fixture: several tests place a sale on a
    window boundary to the second, which a day-granularity helper could not express.
    """

    batches: dict[int, Batch] = {}

    def _batch_for(medicine: Medicine) -> Batch:
        if medicine.id not in batches:
            batch = Batch(
                medicine_id=medicine.id,
                batch_number=f"B{medicine.id}",
                expiry_date=AS_OF + timedelta(days=365),
                quantity=1000,
                cost_price=Decimal("10.00"),
            )
            db_session.add(batch)
            db_session.flush()
            batches[medicine.id] = batch
        return batches[medicine.id]

    def _sell(name: str, units: int, at_instant: datetime) -> None:
        medicine = medicines[name]
        batch = _batch_for(medicine)
        sale = Sale(
            customer_id=None,
            total_amount=Decimal(units) * medicine.mrp,
            sold_at=at_instant,
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

    return _sell


def window(days: int = 90) -> DemandWindow:
    return DemandWindow.trailing(lookback_days=days, as_of=AS_OF)


def at(days_ago: int, hour: int = 12) -> datetime:
    return datetime.combine(AS_OF - timedelta(days=days_ago), time(hour, 0))


# ---------------------------------------------------------------------------
# The window itself
# ---------------------------------------------------------------------------


def test_the_window_is_half_open_and_midnight_aligned():
    span = DemandWindow.trailing(lookback_days=90, as_of=AS_OF)

    assert span.start == datetime(2026, 4, 1, 0, 0)
    assert span.end == datetime(2026, 6, 30, 0, 0), "today is excluded"
    assert span.days == 90


def test_the_window_spans_exactly_the_days_it_divides_by():
    """The divisor must match the span, or the average is not an average."""

    span = DemandWindow.trailing(lookback_days=30, as_of=AS_OF)

    assert (span.end - span.start).days == span.days


def test_a_window_defaults_to_today_in_the_pharmacy_timezone(monkeypatch):
    """Not the system clock. The reorder repository read the system clock and the
    expiry repository did not, which is exactly how the two drifted apart.

    Patched through the module, not by importing the name here: ``from x import f``
    binds by value, so patching the source module is the only thing the service sees.
    """

    import app.services.demand_service as module

    monkeypatch.setattr(module, "today", lambda: date(2026, 1, 15))

    assert DemandWindow.trailing(lookback_days=7).end == datetime(2026, 1, 15, 0, 0)


def test_a_zero_day_window_is_rejected():
    with pytest.raises(ValueError, match="at least one day"):
        DemandWindow.trailing(lookback_days=0, as_of=AS_OF)


def test_a_negative_window_is_rejected():
    with pytest.raises(ValueError, match="at least one day"):
        DemandWindow.trailing(lookback_days=-5, as_of=AS_OF)


def test_the_window_describes_what_it_measured():
    assert "2026-04-01" in window().describe()
    assert "90 day(s)" in window().describe()


# ---------------------------------------------------------------------------
# Units sold — the boundaries
# ---------------------------------------------------------------------------


def test_no_sales_at_all_returns_an_empty_mapping(service):
    assert service.units_sold(window()) == {}


def test_one_sale_is_counted(service, sell, medicines, db_session):
    sell("Crocin 500", 10, at(days_ago=5))
    db_session.commit()

    assert service.units_sold(window())[medicines["Crocin 500"].id] == 10


def test_many_sales_of_one_medicine_are_summed(service, sell, medicines, db_session):
    sell("Crocin 500", 10, at(days_ago=5))
    sell("Crocin 500", 7, at(days_ago=40))
    sell("Crocin 500", 3, at(days_ago=89))
    db_session.commit()

    assert service.units_sold(window())[medicines["Crocin 500"].id] == 20


def test_a_sale_exactly_at_the_start_boundary_is_included(
    service, sell, medicines, db_session
):
    """Midnight on the first day of the window. Inclusive lower bound."""

    sell("Crocin 500", 4, window().start)
    db_session.commit()

    assert service.units_sold(window())[medicines["Crocin 500"].id] == 4


def test_a_sale_one_second_before_the_start_is_excluded(
    service, sell, medicines, db_session
):
    sell("Crocin 500", 4, window().start - timedelta(seconds=1))
    db_session.commit()

    assert service.units_sold(window()) == {}


def test_a_sale_exactly_at_the_end_boundary_is_excluded(
    service, sell, medicines, db_session
):
    """Midnight today. Exclusive upper bound — today has not finished trading."""

    sell("Crocin 500", 4, window().end)
    db_session.commit()

    assert service.units_sold(window()) == {}


def test_a_sale_one_second_before_the_end_is_included(
    service, sell, medicines, db_session
):
    sell("Crocin 500", 4, window().end - timedelta(seconds=1))
    db_session.commit()

    assert service.units_sold(window())[medicines["Crocin 500"].id] == 4


def test_todays_partial_trading_does_not_drag_the_average_down(
    service, sell, medicines, db_session
):
    """A sale at 10am today is real, but counting it against a whole day of window
    would make the same report give different answers at 10am and at 6pm."""

    sell("Crocin 500", 500, datetime.combine(AS_OF, time(10, 0)))
    db_session.commit()

    assert service.units_sold(window()) == {}


def test_a_sale_outside_the_lookback_is_excluded(service, sell, medicines, db_session):
    sell("Crocin 500", 50, at(days_ago=200))
    db_session.commit()

    assert service.units_sold(window(90)) == {}


def test_a_longer_lookback_reaches_the_older_sale(service, sell, medicines, db_session):
    sell("Crocin 500", 50, at(days_ago=200))
    db_session.commit()

    assert service.units_sold(window(365))[medicines["Crocin 500"].id] == 50


def test_a_future_dated_sale_is_excluded(service, sell, medicines, db_session):
    """The old reorder query had no upper bound at all, so this counted as recent."""

    sell("Crocin 500", 99, datetime.combine(AS_OF + timedelta(days=3), time(9, 0)))
    db_session.commit()

    assert service.units_sold(window()) == {}


# ---------------------------------------------------------------------------
# Units sold — several medicines
# ---------------------------------------------------------------------------


def test_medicines_are_counted_separately(service, sell, medicines, db_session):
    sell("Crocin 500", 10, at(days_ago=5))
    sell("Dolo 650", 25, at(days_ago=5))
    db_session.commit()

    units = service.units_sold(window())

    assert units[medicines["Crocin 500"].id] == 10
    assert units[medicines["Dolo 650"].id] == 25


def test_a_medicine_that_never_sold_is_absent_rather_than_zero(
    service, sell, medicines, db_session
):
    """Absent and zero mean different things: one is "no data", the other would claim
    the medicine is known to sell nothing."""

    sell("Crocin 500", 10, at(days_ago=5))
    db_session.commit()

    assert medicines["Dolo 650"].id not in service.units_sold(window())


def test_the_result_can_be_restricted_to_specific_medicines(
    service, sell, medicines, db_session
):
    sell("Crocin 500", 10, at(days_ago=5))
    sell("Dolo 650", 25, at(days_ago=5))
    db_session.commit()

    units = service.units_sold(window(), medicine_ids=[medicines["Crocin 500"].id])

    assert set(units) == {medicines["Crocin 500"].id}


def test_an_empty_medicine_list_means_every_medicine(
    service, sell, medicines, db_session
):
    """Preserved from the expiry repository deliberately. Making an empty list mean
    "nothing" would silently empty the expiry report."""

    sell("Crocin 500", 10, at(days_ago=5))
    db_session.commit()

    assert service.units_sold(window(), medicine_ids=[]) != {}


# ---------------------------------------------------------------------------
# The velocity formula
# ---------------------------------------------------------------------------


def test_velocity_is_units_over_the_whole_window():
    assert daily_velocity(180, 90) == 2.0


def test_velocity_of_no_sales_is_zero():
    assert daily_velocity(0, 30) == 0.0


def test_velocity_is_floored_at_zero():
    """Negative quantity is reachable — there is no CHECK constraint on the column —
    and a negative velocity would flow straight into a days-of-cover division."""

    assert daily_velocity(-40, 30) == 0.0


def test_velocity_rejects_a_zero_day_window():
    with pytest.raises(ValueError, match="at least 1"):
        daily_velocity(10, 0)


def test_velocity_is_computed_per_medicine(service, sell, medicines, db_session):
    sell("Crocin 500", 180, at(days_ago=30))
    sell("Dolo 650", 900, at(days_ago=30))
    db_session.commit()

    velocity = service.daily_velocity(window(90))

    assert velocity[medicines["Crocin 500"].id] == 2.0
    assert velocity[medicines["Dolo 650"].id] == 10.0


def test_a_shorter_window_raises_the_velocity(service, sell, medicines, db_session):
    """Same sale, half the window, double the rate. The lookback is a business choice
    and must visibly change the answer."""

    sell("Crocin 500", 90, at(days_ago=10))
    db_session.commit()

    assert service.daily_velocity(window(90))[medicines["Crocin 500"].id] == 1.0
    assert service.daily_velocity(window(45))[medicines["Crocin 500"].id] == 2.0


# ---------------------------------------------------------------------------
# Last sale date
# ---------------------------------------------------------------------------


def test_the_last_sale_date_is_the_most_recent_one(service, sell, medicines, db_session):
    sell("Crocin 500", 5, at(days_ago=100))
    sell("Crocin 500", 5, at(days_ago=3))
    sell("Crocin 500", 5, at(days_ago=40))
    db_session.commit()

    dates = service.last_sale_dates()

    assert dates[medicines["Crocin 500"].id] == AS_OF - timedelta(days=3)


def test_the_last_sale_date_is_not_bounded_by_any_window(
    service, sell, medicines, db_session
):
    """A dead medicine's last sale is years back. Bounding it to a window would make
    dead stock indistinguishable from a brisk seller."""

    sell("Crocin 500", 5, at(days_ago=900))
    db_session.commit()

    assert service.last_sale_dates()[medicines["Crocin 500"].id] == AS_OF - timedelta(
        days=900
    )


def test_a_medicine_never_sold_has_no_last_sale_date(
    service, sell, medicines, db_session
):
    sell("Crocin 500", 5, at(days_ago=3))
    db_session.commit()

    assert medicines["Dolo 650"].id not in service.last_sale_dates()


def test_last_sale_dates_on_an_empty_database_are_empty(service):
    assert service.last_sale_dates() == {}


def test_last_sale_dates_can_be_restricted(service, sell, medicines, db_session):
    sell("Crocin 500", 5, at(days_ago=3))
    sell("Dolo 650", 5, at(days_ago=3))
    db_session.commit()

    dates = service.last_sale_dates(medicine_ids=[medicines["Dolo 650"].id])

    assert set(dates) == {medicines["Dolo 650"].id}


def test_a_last_sale_date_is_a_date_not_a_timestamp(
    service, sell, medicines, db_session
):
    """Callers ask "how long ago". Handing back a timestamp invites subtracting two of
    them and getting an answer that changes with the hour."""

    sell("Crocin 500", 5, at(days_ago=3, hour=17))
    db_session.commit()

    value = service.last_sale_dates()[medicines["Crocin 500"].id]

    assert isinstance(value, date) and not isinstance(value, datetime)


# ---------------------------------------------------------------------------
# Ever sold
# ---------------------------------------------------------------------------


def test_ever_sold_separates_slow_movers_from_new_stock(
    service, sell, medicines, db_session
):
    sell("Crocin 500", 50, at(days_ago=200))
    db_session.commit()

    ever_sold = service.medicines_ever_sold(
        [medicines["Crocin 500"].id, medicines["Dolo 650"].id]
    )

    assert medicines["Crocin 500"].id in ever_sold, "sold long ago, but it has history"
    assert medicines["Dolo 650"].id not in ever_sold, "never sold at all"


def test_ever_sold_handles_an_empty_list(service):
    """An empty IN clause is a SQL error in some dialects; short-circuit instead."""

    assert service.medicines_ever_sold([]) == set()
