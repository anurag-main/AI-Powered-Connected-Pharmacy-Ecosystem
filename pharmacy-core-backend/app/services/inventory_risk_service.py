"""Deterministic inventory-risk calculation.

No LLM anywhere in this file. Every number is computed here, in Python, from database
facts — stock, value, velocity, cover, excess, capital at risk, age, risk level and
the reasons behind it. A model will later put this into English and will not be
allowed to change a digit of it.

--------------------------------------------------------------------------------
THE QUESTION THIS ANSWERS
--------------------------------------------------------------------------------
"Which inventory is absorbing capital it shouldn't?"

Not "what is running out" — the Reorder agent owns that. Not "what will expire before
it sells" — the Expiry agent owns that, and this file deliberately never mentions an
expiry date in its output. The two would otherwise be the same screen twice.

The measured case for building it: of 96 stocked medicines in the production
database, 84 hold more than 120 days of cover, worth Rs 26.2 lakh, and no existing
report surfaces one of them.

--------------------------------------------------------------------------------
CAPITAL IS NOT COVER
--------------------------------------------------------------------------------
Expired stock is money already spent. It counts toward what a pharmacist has tied up,
and counts for nothing toward how long the shelf will last. So two stock figures flow
through this file and are never mixed:

    stock_quantity      every positive batch        -> value, capital at risk
    sellable_quantity   non-expired batches only    -> cover, target, excess

--------------------------------------------------------------------------------
THIS IS MEASUREMENT, NOT FORECASTING
--------------------------------------------------------------------------------
Velocity is the recent daily average from ``DemandService``, projected flat. No
seasonality, no trend, no confidence interval. Days of cover is arithmetic on that
average, not a prediction of a stockout date. The Forecast Agent is a later milestone
and this file must not grow into one.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import date

from app.ai.schemas.inventory_query import (
    RISK_ORDER,
    InventoryRiskItem,
    InventoryRiskLevel,
    InventoryRiskQuery,
    InventoryRiskReport,
    InventorySort,
)
from app.core.time_range import today
from app.repositories.inventory_repository import InventoryRepository, MedicineStock
from app.services.demand_service import DemandService, DemandWindow, daily_velocity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InventoryRiskConfig:
    """Every threshold in one place, each one explained and overridable by env var.

    None of these is a fact about the world; they are business policy, and a
    pharmacist with different cash flow would set them differently. That is exactly
    why they are named constants read from the environment rather than numbers buried
    in an ``if``.
    """

    #: NOTE: how much cover the shop *wants* to hold is NOT here. It lives on
    #: ``InventoryRiskQuery.target_cover_days``, because it is a question a caller
    #: asks ("what if I only held 30 days?"), not a deployment setting. The
    #: thresholds below ARE deployment settings: they decide when an amount of cover
    #: becomes a problem worth showing.

    #: Four months of cover. Twice the target: past here, stock is not a buffer any
    #: more, it is storage.
    overstock_cover_days: int = 120

    #: Six months. Half a year of capital in one product.
    high_cover_days: int = 180

    #: A year of cover. Most pharmaceutical stock carries a two-year shelf life, so
    #: past this point there is a real chance of never selling it at all.
    critical_cover_days: int = 365

    #: No sale in six months, with stock still on the shelf. Long enough to survive a
    #: seasonal product's off season, short enough to catch a genuinely dead line.
    dead_stock_days: int = 180

    #: Rupee gates. Cover alone would rank a Rs 40 slow mover above a Rs 40,000 one,
    #: which is the wrong advice: the pharmacist has finite attention and should
    #: spend it where the money is. A medicine qualifies for a level by EITHER its
    #: cover or its trapped capital.
    medium_value: float = 2_000.0
    high_value: float = 10_000.0
    critical_value: float = 25_000.0

    #: Matches the expiry agent's lookback. Long enough to smooth week-to-week noise,
    #: short enough to reflect how the product sells now.
    demand_lookback_days: int = 90

    @classmethod
    def from_env(cls) -> "InventoryRiskConfig":
        def read_int(name: str, default: int) -> int:
            raw = os.environ.get(name)
            if raw is None or not raw.strip():
                return default
            try:
                value = int(raw)
            except ValueError as exc:
                raise RuntimeError(f"{name} must be a whole number, got {raw!r}") from exc
            if value < 1:
                raise RuntimeError(f"{name} must be at least 1, got {value}")
            return value

        def read_money(name: str, default: float) -> float:
            raw = os.environ.get(name)
            if raw is None or not raw.strip():
                return default
            try:
                value = float(raw)
            except ValueError as exc:
                raise RuntimeError(f"{name} must be a number, got {raw!r}") from exc
            if value < 0:
                raise RuntimeError(f"{name} must not be negative, got {value}")
            return value

        config = cls(
            overstock_cover_days=read_int(
                "INVENTORY_OVERSTOCK_COVER_DAYS", cls.overstock_cover_days
            ),
            high_cover_days=read_int("INVENTORY_HIGH_COVER_DAYS", cls.high_cover_days),
            critical_cover_days=read_int(
                "INVENTORY_CRITICAL_COVER_DAYS", cls.critical_cover_days
            ),
            dead_stock_days=read_int("INVENTORY_DEAD_STOCK_DAYS", cls.dead_stock_days),
            medium_value=read_money("INVENTORY_MEDIUM_VALUE", cls.medium_value),
            high_value=read_money("INVENTORY_HIGH_VALUE", cls.high_value),
            critical_value=read_money("INVENTORY_CRITICAL_VALUE", cls.critical_value),
            demand_lookback_days=read_int(
                "INVENTORY_DEMAND_LOOKBACK_DAYS", cls.demand_lookback_days
            ),
        )

        # Overlapping thresholds would make a risk level unreachable and the report
        # silently misleading, so this fails at construction rather than at runtime.
        if not (
            config.overstock_cover_days
            < config.high_cover_days
            < config.critical_cover_days
        ):
            raise RuntimeError(
                "Inventory cover thresholds must satisfy overstock < high < critical; "
                f"got {config.overstock_cover_days} / {config.high_cover_days} / "
                f"{config.critical_cover_days}"
            )

        if not config.medium_value < config.high_value < config.critical_value:
            raise RuntimeError(
                "Inventory value thresholds must satisfy medium < high < critical; "
                f"got {config.medium_value} / {config.high_value} / "
                f"{config.critical_value}"
            )

        return config


def _empty_counts() -> dict[str, int]:
    return {level.value: 0 for level in InventoryRiskLevel}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class InventoryRiskService:
    """Turns stock facts and sales history into a ranked, explained capital report."""

    def __init__(
        self,
        repository: InventoryRepository,
        demand: DemandService,
        config: InventoryRiskConfig | None = None,
    ) -> None:
        self.repository = repository
        self.demand = demand
        self.config = config or InventoryRiskConfig.from_env()

    # -- entry point ----------------------------------------------------

    def assess(
        self,
        query: InventoryRiskQuery | None = None,
        *,
        as_of: date | None = None,
    ) -> InventoryRiskReport:
        """Produce the inventory-risk report for one validated query.

        The query is optional so the service stays usable — and testable — without an
        HTTP layer above it. Omitting it means the default: every stocked medicine,
        ranked by risk, top 10.

        Order of operations matters and is deliberate:

            assess every stocked medicine   -> shop-level totals and counts
            filter                          -> what the caller asked for
            sort                            -> how they asked for it
            limit                           -> how much they can read

        Totals and ``counts_by_risk`` are taken from the FULL set, before filtering.
        They are shop-level KPIs: a dashboard filtered to dead stock should still be
        able to say what the whole shop has tied up. ``items_matching_filter`` carries
        the filtered count so the caller can say "showing 10 of 84".
        """

        query = query or InventoryRiskQuery()
        reference = as_of or today()

        stocks = self.repository.stock_by_medicine(as_of=reference)
        total_medicines = self.repository.count_medicines()

        if not stocks:
            return InventoryRiskReport(
                generated_for=reference,
                demand_lookback_days=self.config.demand_lookback_days,
                target_cover_days=query.target_cover_days,
                medicines_reviewed=0,
                items_matching_filter=0,
                capital_at_risk_in_view=0.0,
                medicines_without_stock=total_medicines,
                total_inventory_value=0.0,
                total_capital_at_risk=0.0,
                items=[],
                counts_by_risk=_empty_counts(),
                notes=["No medicine currently holds stock."],
            )

        medicine_ids = [stock.medicine_id for stock in stocks]

        window = DemandWindow.trailing(
            as_of=reference, lookback_days=self.config.demand_lookback_days
        )
        units_sold = self.demand.units_sold(window, medicine_ids=medicine_ids)
        last_sales = self.demand.last_sale_dates(medicine_ids=medicine_ids)
        ever_sold = self.demand.medicines_ever_sold(medicine_ids)
        receipts = self.repository.oldest_receipt_by_medicine(medicine_ids=medicine_ids)

        items = [
            self._assess_medicine(
                stock,
                units_sold=units_sold.get(stock.medicine_id, 0),
                last_sale=last_sales.get(stock.medicine_id),
                ever_sold=stock.medicine_id in ever_sold,
                received_on=receipts.get(stock.medicine_id),
                reference=reference,
                target_cover_days=query.target_cover_days,
            )
            for stock in stocks
        ]

        # Shop-level figures, taken before any filter narrows the view.
        totals_value = round(sum(i.inventory_value for i in items), 2)
        totals_at_risk = round(sum(i.capital_at_risk for i in items), 2)
        counts = _count_by_risk(items)

        matching = self._filter(items, query)
        matching.sort(key=_sort_key(query.sort))

        report = InventoryRiskReport(
            generated_for=reference,
            demand_lookback_days=self.config.demand_lookback_days,
            target_cover_days=query.target_cover_days,
            medicines_reviewed=len(items),
            medicines_without_stock=max(0, total_medicines - len(items)),
            items_matching_filter=len(matching),
            total_inventory_value=totals_value,
            total_capital_at_risk=totals_at_risk,
            capital_at_risk_in_view=round(sum(i.capital_at_risk for i in matching), 2),
            items=matching[: query.limit],
            counts_by_risk=counts,
            notes=self._build_notes(stocks, items, receipts, query.target_cover_days),
        )

        logger.info(
            "inventory_risk_assessed",
            extra={
                "medicines_reviewed": report.medicines_reviewed,
                "matching": report.items_matching_filter,
                "target_cover_days": query.target_cover_days,
                "sort": query.sort.value,
            },
        )

        return report

    # -- filtering ------------------------------------------------------

    @staticmethod
    def _filter(
        items: list[InventoryRiskItem], query: InventoryRiskQuery
    ) -> list[InventoryRiskItem]:
        """Narrow the assessed set to what the caller asked for.

        A separate pass over already-computed items rather than a WHERE clause: the
        risk level and capital at risk are Python-side conclusions, not columns, so
        there is nothing for SQL to filter on. The set is at most a few hundred rows.
        """

        matching = items

        if query.risk_level is not None:
            matching = [i for i in matching if i.risk_level is query.risk_level]

        if query.min_capital_at_risk > 0:
            matching = [
                i for i in matching if i.capital_at_risk >= query.min_capital_at_risk
            ]

        if query.medicine_id is not None:
            matching = [i for i in matching if i.medicine_id == query.medicine_id]

        return list(matching)

    # -- one medicine ---------------------------------------------------

    def _assess_medicine(
        self,
        stock: MedicineStock,
        *,
        units_sold: int,
        last_sale: date | None,
        ever_sold: bool,
        received_on: date | None,
        reference: date,
        target_cover_days: int,
    ) -> InventoryRiskItem:
        inventory_value = float(stock.inventory_value)
        weighted_avg_cost = self._weighted_avg_cost(inventory_value, stock.stock_quantity)

        daily_velocity = self.demand_velocity(units_sold)
        days_of_cover = self._days_of_cover(stock.sellable_quantity, daily_velocity)

        target_stock = math.ceil(daily_velocity * target_cover_days)
        excess_units = max(0, stock.sellable_quantity - target_stock)
        excess_value = round(excess_units * weighted_avg_cost, 2)

        days_since_last_sale = (reference - last_sale).days if last_sale else None
        stock_age_days = (reference - received_on).days if received_on else None

        level = self._risk_level(
            excess_value=excess_value,
            days_of_cover=days_of_cover,
            ever_sold=ever_sold,
            days_since_last_sale=days_since_last_sale,
        )

        capital_at_risk = self._capital_at_risk(level, inventory_value, excess_value)

        return InventoryRiskItem(
            medicine_id=stock.medicine_id,
            medicine_name=stock.medicine_name,
            stock_quantity=stock.stock_quantity,
            inventory_value=round(inventory_value, 2),
            sellable_quantity=stock.sellable_quantity,
            weighted_avg_cost=weighted_avg_cost,
            units_sold=units_sold,
            daily_velocity=daily_velocity,
            days_of_cover=days_of_cover,
            last_sale_date=last_sale,
            days_since_last_sale=days_since_last_sale,
            ever_sold=ever_sold,
            target_stock=target_stock,
            excess_units=excess_units,
            excess_value=excess_value,
            capital_at_risk=capital_at_risk,
            oldest_receipt_date=received_on,
            stock_age_days=stock_age_days,
            risk_level=level,
            risk_reasons=self._reasons(
                stock=stock,
                daily_velocity=daily_velocity,
                days_of_cover=days_of_cover,
                excess_units=excess_units,
                excess_value=excess_value,
                ever_sold=ever_sold,
                days_since_last_sale=days_since_last_sale,
                stock_age_days=stock_age_days,
                level=level,
                target_cover_days=target_cover_days,
            ),
        )

    # -- formulas -------------------------------------------------------

    def demand_velocity(self, units_sold: int) -> float:
        """Units per day, through the formula every stock agent shares.

        Thin by design. The division itself lives in ``demand_service`` so this agent
        cannot drift away from expiry and reorder.
        """

        return daily_velocity(units_sold, self.config.demand_lookback_days)

    @staticmethod
    def _weighted_avg_cost(inventory_value: float, stock_quantity: int) -> float:
        """Value per unit across all of a medicine's batches.

        Weighted, because two batches of the same medicine are routinely bought at
        different prices and taking either one's ``cost_price`` would misvalue the
        excess. Guarded against a zero divisor even though the repository only returns
        medicines with positive stock — the guard costs nothing and the invariant is
        one refactor away from being someone else's assumption.
        """

        if stock_quantity <= 0:
            return 0.0
        return round(inventory_value / stock_quantity, 4)

    @staticmethod
    def _days_of_cover(sellable_quantity: int, daily_velocity: float) -> float | None:
        """How long the sellable stock lasts at the current rate.

        **Returns ``None``, not infinity, when nothing is selling.**

        Infinity is the tempting answer and it is the wrong one here. ``inf`` compares
        greater than every cover threshold, so a never-sold medicine would be
        classified as overstock by the cover rule — describing a product with no sales
        history as "holding 365+ days of cover", which is a statement about a rate
        that was never measured. ``None`` has no ordering, so the classifier is forced
        to reach the dead-stock rule instead, which is the honest description.

        The reorder agent returns ``inf`` from its own ``days_of_cover`` and that is
        correct *there*: it is asking "is this urgent", and never-sold stock is never
        urgent to reorder. Different question, different right answer.
        """

        if daily_velocity <= 0:
            return None
        return round(sellable_quantity / daily_velocity, 1)

    def _capital_at_risk(
        self, level: InventoryRiskLevel, inventory_value: float, excess_value: float
    ) -> float:
        """The money this medicine is absorbing that it should not be.

        Deliberately **not** the whole inventory value in the general case. A shop
        must hold stock to trade; the target cover is capital doing its job. Only the
        part above target is trapped::

            dead stock  ->  inventory_value   nothing is moving, all of it is stuck
            otherwise   ->  excess_value      the part above the target

        Dead stock takes the full value including expired batches, because none of it
        is coming back through the till.
        """

        if level is InventoryRiskLevel.DEAD:
            return round(inventory_value, 2)
        return excess_value

    # -- classification -------------------------------------------------

    def _risk_level(
        self,
        *,
        excess_value: float,
        days_of_cover: float | None,
        ever_sold: bool,
        days_since_last_sale: int | None,
    ) -> InventoryRiskLevel:
        """Classify one medicine. Checked worst-first; first match wins.

        Every level is reachable by EITHER trapped capital OR days of cover. Cover
        alone would rank a Rs 40 slow mover above a Rs 40,000 one; capital alone would
        miss a large pile of cheap stock that will never move.
        """

        # Dead first: it is a statement about movement, and a medicine with no
        # movement has no meaningful cover figure to classify on.
        if not ever_sold:
            return InventoryRiskLevel.DEAD
        if (
            days_since_last_sale is not None
            and days_since_last_sale >= self.config.dead_stock_days
        ):
            return InventoryRiskLevel.DEAD

        # A medicine that sold recently but has no velocity in the window is a very
        # slow mover, not dead. It has no cover figure, so only capital can rank it.
        cover = days_of_cover

        if excess_value >= self.config.critical_value or (
            cover is not None and cover > self.config.critical_cover_days
        ):
            return InventoryRiskLevel.CRITICAL

        if excess_value >= self.config.high_value or (
            cover is not None and cover > self.config.high_cover_days
        ):
            return InventoryRiskLevel.HIGH

        if excess_value >= self.config.medium_value or (
            cover is not None and cover > self.config.overstock_cover_days
        ):
            return InventoryRiskLevel.MEDIUM

        return InventoryRiskLevel.HEALTHY

    def _reasons(
        self,
        *,
        stock: MedicineStock,
        daily_velocity: float,
        days_of_cover: float | None,
        excess_units: int,
        excess_value: float,
        ever_sold: bool,
        days_since_last_sale: int | None,
        stock_age_days: int | None,
        level: InventoryRiskLevel,
        target_cover_days: int,
    ) -> list[str]:
        """Plain facts that add up to the level. No adjectives, no advice.

        Every line is checkable against the item's own fields. This is what makes the
        classification defensible without a score: a pharmacist can disagree with the
        threshold, but not with the arithmetic.
        """

        reasons = [f"{stock.stock_quantity} unit(s) in stock"]

        expired_units = stock.stock_quantity - stock.sellable_quantity
        if expired_units > 0:
            # Stated as a count, never as a date. Expiry dates belong to the expiry
            # agent; repeating them here would make the two reports interchangeable.
            reasons.append(f"{expired_units} unit(s) no longer sellable")

        if not ever_sold:
            reasons.append("never sold")
        elif days_since_last_sale is not None:
            reasons.append(f"last sold {days_since_last_sale} day(s) ago")

        if daily_velocity > 0:
            reasons.append(f"selling {daily_velocity:.2f} unit(s)/day")
        else:
            reasons.append(
                f"no sales in the last {self.config.demand_lookback_days} day(s)"
            )

        if days_of_cover is not None:
            reasons.append(f"{days_of_cover:g} day(s) of cover")

        if excess_units > 0:
            reasons.append(
                f"{excess_units} unit(s) above a {target_cover_days}-day "
                f"target, worth Rs {excess_value:,.2f}"
            )

        if stock_age_days is not None:
            reasons.append(f"oldest stock received {stock_age_days} day(s) ago")

        if level is InventoryRiskLevel.HEALTHY:
            reasons.append("within the target cover")

        return reasons

    # -- notes ----------------------------------------------------------

    def _build_notes(
        self,
        stocks: list[MedicineStock],
        items: list[InventoryRiskItem],
        receipts: dict[int, date],
        target_cover_days: int,
    ) -> list[str]:
        """What the reader needs in order to trust, or distrust, the numbers."""

        notes = [
            "Velocity is the average over the last "
            f"{self.config.demand_lookback_days} days, projected flat. It is an "
            "estimate from history, not a forecast.",
            "Capital at risk is stock above the "
            f"{target_cover_days}-day target, or the full value of stock "
            "classified as dead.",
        ]

        missing_age = len(items) - len(receipts)
        if missing_age > 0:
            notes.append(
                f"{missing_age} medicine(s) have no purchase record for the stock they "
                "hold, so their stock age is unknown rather than zero."
            )

        negative = sum(1 for stock in stocks if stock.negative_batch_count > 0)
        if negative:
            notes.append(
                f"{negative} medicine(s) have batches with negative quantity. Those "
                "batches are excluded from the totals and should be corrected."
            )

        return notes


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def _ranking_key(item: InventoryRiskItem) -> tuple:
    """Worst risk first, then most money, with a total order guaranteed.

    Deliberately **not** a computed priority score. An earlier design multiplied
    excess value by a stock-age factor, which produces a number that looks precise,
    cannot be checked by hand, and hides which of the two inputs drove the ranking.
    Sorting on the facts themselves is defensible all the way down.

    ``medicine_id`` last makes the order total, so two identical positions always come
    back the same way and a ranking cannot flap between runs.
    """

    return (
        RISK_ORDER[item.risk_level],
        -item.capital_at_risk,
        -item.inventory_value,
        item.medicine_id,
    )


#: Sorts last. Larger than any real cover figure or stock age, so a medicine with
#: no measurable rate never displaces one that has a real number.
_UNKNOWN_LAST = float("-inf")


def _sort_key(sort: InventorySort):
    """Pick the ordering function for a validated sort option.

    Every option ends in ``medicine_id`` so the order is total. Without it two
    identical positions could come back either way round and a table would appear to
    reshuffle itself between refreshes.

    ``None`` is mapped to ``-inf`` under a descending sort, which puts "not known"
    last. Treating it as zero would be a claim; treating it as infinity would rank a
    medicine nobody can measure above every medicine somebody can.
    """

    if sort is InventorySort.CAPITAL:
        return lambda i: (-i.capital_at_risk, -i.inventory_value, i.medicine_id)

    if sort is InventorySort.COVER:
        return lambda i: (
            -(i.days_of_cover if i.days_of_cover is not None else _UNKNOWN_LAST),
            i.medicine_id,
        )

    if sort is InventorySort.STOCK_AGE:
        return lambda i: (
            -(i.stock_age_days if i.stock_age_days is not None else _UNKNOWN_LAST),
            i.medicine_id,
        )

    return _ranking_key


def _count_by_risk(items: list[InventoryRiskItem]) -> dict[str, int]:
    """Counted over every item, before any limit the caller applies later.

    The expiry agent learned this the hard way: counting rows after a ``limit`` caps
    every summary card at the limit and quietly understates the problem.
    """

    counts = _empty_counts()
    for item in items:
        counts[item.risk_level.value] += 1
    return counts
