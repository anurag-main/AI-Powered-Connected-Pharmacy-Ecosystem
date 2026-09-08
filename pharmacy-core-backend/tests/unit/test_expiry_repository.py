"""ExpiryRepository — the SQL behind the risk calculation.

The repository does no risk logic. What it must get right is the window, the ordering
the service depends on, and the demand aggregate's boundaries.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.batch import Batch
from app.models.medicine import Medicine
from app.repositories.expiry_repository import ExpiryRepository

pytestmark = pytest.mark.unit


@pytest.fixture
def repository(expiry_db) -> ExpiryRepository:
    return ExpiryRepository(expiry_db)


@pytest.fixture
def empty_repository(db_session) -> ExpiryRepository:
    return ExpiryRepository(db_session)


def numbers(batches) -> list[str]:
    return [batch.batch_number for batch in batches]


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------


def test_only_batches_inside_the_window_are_returned(repository, expiry_as_of):
    found = repository.batches_in_window(as_of=expiry_as_of, window_days=30)

    assert "Z1" not in numbers(found), "expires in 300 days"
    assert {"P1", "P2", "A1", "V1", "C1"} == set(numbers(found))


def test_the_window_boundary_is_inclusive(repository, expiry_as_of):
    """A batch expiring exactly on the cutoff must be included. Excluding it would
    hide the item a "next 20 days" question is most likely about."""

    found = repository.batches_in_window(as_of=expiry_as_of, window_days=20)

    assert "P2" in numbers(found), "P2 expires exactly 20 days out"


def test_one_day_short_of_the_boundary_excludes_it(repository, expiry_as_of):
    found = repository.batches_in_window(as_of=expiry_as_of, window_days=19)

    assert "P2" not in numbers(found)


def test_expired_batches_are_included_by_default(repository, expiry_as_of):
    found = repository.batches_in_window(as_of=expiry_as_of, window_days=7)

    assert "C1" in numbers(found)


def test_expired_batches_can_be_excluded(repository, expiry_as_of):
    found = repository.batches_in_window(
        as_of=expiry_as_of, window_days=365, include_expired=False
    )

    assert "C1" not in numbers(found)


def test_filtering_to_one_medicine(repository, expiry_as_of, expiry_db):
    paracetamol = expiry_db.query(Medicine).filter_by(name="Paracetamol 500").one()

    found = repository.batches_in_window(
        as_of=expiry_as_of, window_days=365, medicine_id=paracetamol.id
    )

    assert set(numbers(found)) == {"P1", "P2"}


def test_an_empty_database_returns_nothing(empty_repository, expiry_as_of):
    assert empty_repository.batches_in_window(as_of=expiry_as_of, window_days=90) == []


# ---------------------------------------------------------------------------
# Ordering — the service depends on this
# ---------------------------------------------------------------------------


def test_batches_come_back_in_fefo_order_within_a_medicine(repository, expiry_as_of):
    """The service walks this order to allocate demand, so getting it wrong would
    silently attribute the early demand to the wrong batch."""

    found = repository.batches_in_window(as_of=expiry_as_of, window_days=365)
    paracetamol = [b for b in found if b.batch_number.startswith("P")]

    assert numbers(paracetamol) == ["P1", "P2"]
    assert paracetamol[0].expiry_date < paracetamol[1].expiry_date


def test_batches_are_grouped_by_medicine(repository, expiry_as_of):
    """Grouping in the service is a single pass, which assumes rows arrive together."""

    found = repository.batches_in_window(as_of=expiry_as_of, window_days=365)
    medicine_ids = [batch.medicine_id for batch in found]

    # Each medicine id appears in one contiguous run.
    seen: list[int] = []
    for medicine_id in medicine_ids:
        if not seen or seen[-1] != medicine_id:
            assert medicine_id not in seen, "rows for one medicine were split up"
            seen.append(medicine_id)


def test_batches_sharing_an_expiry_date_order_by_id(expiry_db, expiry_as_of):
    """Without the id tiebreak the order is whatever the engine feels like, and the
    final ranking could differ between two runs on identical data."""

    amox = expiry_db.query(Medicine).filter_by(name="Amoxicillin 250").one()
    expiry_db.add(
        Batch(
            medicine_id=amox.id,
            batch_number="A2",
            expiry_date=expiry_as_of + timedelta(days=10),
            quantity=10,
            cost_price=Decimal("20.00"),
        )
    )
    expiry_db.commit()

    found = ExpiryRepository(expiry_db).batches_in_window(
        as_of=expiry_as_of, window_days=365
    )
    amox_batches = [b for b in found if b.medicine_id == amox.id]

    assert numbers(amox_batches) == ["A1", "A2"]
    assert amox_batches[0].batch_id < amox_batches[1].batch_id


# ---------------------------------------------------------------------------
# Quantity handling
# ---------------------------------------------------------------------------


def test_zero_quantity_batches_are_skipped(expiry_db, expiry_as_of):
    batch = expiry_db.query(Batch).filter_by(batch_number="A1").one()
    batch.quantity = 0
    expiry_db.commit()

    found = ExpiryRepository(expiry_db).batches_in_window(
        as_of=expiry_as_of, window_days=365
    )

    assert "A1" not in numbers(found)


def test_negative_quantity_batches_are_kept(expiry_db, expiry_as_of):
    """No CHECK constraint exists on the column, so bad data is reachable. Filtering
    it out here would hide a real problem rather than surface it."""

    batch = expiry_db.query(Batch).filter_by(batch_number="A1").one()
    batch.quantity = -5
    expiry_db.commit()

    found = ExpiryRepository(expiry_db).batches_in_window(
        as_of=expiry_as_of, window_days=365
    )

    assert "A1" in numbers(found)


def test_the_batch_carries_everything_the_calculation_needs(repository, expiry_as_of):
    found = repository.batches_in_window(as_of=expiry_as_of, window_days=365)
    p1 = next(b for b in found if b.batch_number == "P1")

    assert p1.medicine_name == "Paracetamol 500"
    assert p1.quantity == 30
    assert p1.cost_price == Decimal("10.00")
    assert p1.expiry_date == expiry_as_of + timedelta(days=5)


# ---------------------------------------------------------------------------
# Demand
# ---------------------------------------------------------------------------


def test_demand_sums_units_sold_in_the_window(repository, expiry_as_of, expiry_db):
    paracetamol = expiry_db.query(Medicine).filter_by(name="Paracetamol 500").one()

    demand = repository.recent_demand(as_of=expiry_as_of, lookback_days=90)

    assert demand[paracetamol.id] == 180


def test_a_sale_outside_the_lookback_is_excluded(repository, expiry_as_of, expiry_db):
    """Cough syrup sold 200 days ago, well outside a 90-day lookback."""

    cough = expiry_db.query(Medicine).filter_by(name="Cough Syrup 100ml").one()

    demand = repository.recent_demand(as_of=expiry_as_of, lookback_days=90)

    assert cough.id not in demand


def test_a_longer_lookback_reaches_the_older_sale(repository, expiry_as_of, expiry_db):
    cough = expiry_db.query(Medicine).filter_by(name="Cough Syrup 100ml").one()

    demand = repository.recent_demand(as_of=expiry_as_of, lookback_days=365)

    assert demand[cough.id] == 50


def test_a_medicine_never_sold_is_absent_rather_than_zero(
    repository, expiry_as_of, expiry_db
):
    """Absent and zero mean different things to the service: one is "no data", the
    other would be "known to sell nothing"."""

    amox = expiry_db.query(Medicine).filter_by(name="Amoxicillin 250").one()

    demand = repository.recent_demand(as_of=expiry_as_of, lookback_days=90)

    assert amox.id not in demand


def test_demand_can_be_restricted_to_specific_medicines(
    repository, expiry_as_of, expiry_db
):
    paracetamol = expiry_db.query(Medicine).filter_by(name="Paracetamol 500").one()

    demand = repository.recent_demand(
        as_of=expiry_as_of, lookback_days=90, medicine_ids=[paracetamol.id]
    )

    assert set(demand) == {paracetamol.id}


def test_demand_on_an_empty_database_is_empty(empty_repository, expiry_as_of):
    assert empty_repository.recent_demand(as_of=expiry_as_of, lookback_days=90) == {}


# ---------------------------------------------------------------------------
# Ever-sold check
# ---------------------------------------------------------------------------


def test_ever_sold_separates_slow_movers_from_new_stock(
    repository, expiry_as_of, expiry_db
):
    cough = expiry_db.query(Medicine).filter_by(name="Cough Syrup 100ml").one()
    amox = expiry_db.query(Medicine).filter_by(name="Amoxicillin 250").one()

    ever_sold = repository.medicines_with_any_sales([cough.id, amox.id])

    assert cough.id in ever_sold, "sold 200 days ago, so it has history"
    assert amox.id not in ever_sold, "never sold at all"


def test_ever_sold_handles_an_empty_list(repository):
    """An empty IN clause is a SQL error in some dialects; short-circuit instead."""

    assert repository.medicines_with_any_sales([]) == set()
