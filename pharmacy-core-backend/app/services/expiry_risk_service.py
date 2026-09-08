"""Deterministic expiry-risk calculation.

No LLM anywhere in this file. Every number the agent reports is computed here, in
Python, from database facts — days remaining, expected demand, excess, value at risk,
risk level and priority. The LLM's only job downstream is to say it in English.

That split is the point of the whole agent. Asking a model "how much of this will
expire?" produces a confident number with nothing behind it. This produces a number
you can check by hand, and a list of reasons explaining how it got there.

--------------------------------------------------------------------------------
THE CENTRAL IDEA: EXPIRY DATE ALONE IS NOT RISK
--------------------------------------------------------------------------------
"Expires in 20 days" is not actionable. 20 units expiring in 20 days when you sell
5 a day is fine — it sells out with room to spare. 500 units expiring in 20 days is
a write-off. What matters is the stock that WON'T sell in time:

    potential excess = stock - demand expected before it expires

--------------------------------------------------------------------------------
DEMAND IS PER MEDICINE, RISK IS PER BATCH
--------------------------------------------------------------------------------
A customer asks for "Crocin", not for batch B7. FEFO decides which batch is opened,
so with three Crocin batches the earliest-expiring one absorbs demand first and the
others only start selling once it is gone.

Dividing a medicine's demand evenly across its batches would therefore understate the
risk on later batches badly. Instead the service walks each medicine's batches in FEFO
order — the same order the billing agent dispenses in — and allocates demand as it
goes:

    Crocin sells 5/day. Two batches:
      B1  30 units, expires in 10 days  -> 50 units of demand available, sells 30
      B2  40 units, expires in 20 days  -> 100 total demand by then, 30 already
                                           taken by B1, so 70 available, sells 40

    Both clear. Now make B1 200 units:
      B1  200 units, expires in 10 days -> 50 available, sells 50, EXCESS 150
      B2   40 units, expires in 20 days -> 100 total, 50 taken, 50 available,
                                           sells 40, excess 0

The second batch is fine precisely because the first one is not selling. That is a
real effect an evenly-divided model would miss entirely.

--------------------------------------------------------------------------------
THIS IS AN ESTIMATE, NOT A FORECAST
--------------------------------------------------------------------------------
Demand is the recent daily average, projected flat. No seasonality, no trend, no
confidence interval. It is honest arithmetic on real sales, and it is labelled
``estimated_demand`` everywhere for that reason. The Forecast Agent replaces it later.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.ai.schemas.expiry_query import (
    RISK_ORDER,
    ExpiryRiskItem,
    ExpiryRiskQuery,
    ExpiryRiskReport,
    RiskLevel,
)
from app.core.time_range import today
from app.repositories.expiry_repository import BatchStock, ExpiryRepository

logger = logging.getLogger("app.services.expiry")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpiryRiskConfig:
    """Thresholds, in one place and overridable by environment.

    The defaults are pharmacy-retail reasonable rather than universal, which is
    exactly why they are configuration and not constants buried in an ``if``.
    """

    # A week is about the shortest window in which a pharmacist can realistically
    # act — run a promotion, call a supplier about a return, move stock.
    critical_days: int = 7

    # A month is the normal planning cycle, and the window most "expiring soon"
    # questions mean.
    warning_days: int = 30

    # A quarter: far enough out that slow movers surface while there is still time
    # to stop reordering them.
    horizon_days: int = 90

    # Long enough to smooth week-to-week noise, short enough to reflect how the
    # product sells NOW rather than last season.
    demand_lookback_days: int = 90

    @classmethod
    def from_env(cls) -> "ExpiryRiskConfig":
        def read(name: str, default: int) -> int:
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

        config = cls(
            critical_days=read("EXPIRY_CRITICAL_DAYS", cls.critical_days),
            warning_days=read("EXPIRY_WARNING_DAYS", cls.warning_days),
            horizon_days=read("EXPIRY_HORIZON_DAYS", cls.horizon_days),
            demand_lookback_days=read(
                "EXPIRY_DEMAND_LOOKBACK_DAYS", cls.demand_lookback_days
            ),
        )

        # Overlapping thresholds would make risk levels unreachable and the report
        # silently misleading, so this fails at construction rather than at runtime.
        if not config.critical_days < config.warning_days <= config.horizon_days:
            raise RuntimeError(
                "Expiry thresholds must satisfy "
                "critical < warning <= horizon; got "
                f"{config.critical_days} / {config.warning_days} / {config.horizon_days}"
            )

        return config


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ExpiryRiskService:
    """Turns stock and sales facts into a ranked, explained risk report."""

    def __init__(
        self,
        repository: ExpiryRepository,
        config: ExpiryRiskConfig | None = None,
    ) -> None:
        self.repository = repository
        self.config = config or ExpiryRiskConfig.from_env()

    # -- entry point ----------------------------------------------------

    def assess(
        self, query: ExpiryRiskQuery, *, as_of: date | None = None
    ) -> ExpiryRiskReport:
        """Produce the expiry-risk report for one validated query."""

        reference = as_of or today()

        batches = self.repository.batches_in_window(
            as_of=reference,
            window_days=query.window_days,
            include_expired=query.include_expired,
            medicine_id=query.medicine_id,
        )

        if not batches:
            return ExpiryRiskReport(
                generated_for=reference,
                window_days=query.window_days,
                demand_lookback_days=self.config.demand_lookback_days,
                total_batches_reviewed=0,
                total_at_risk=0,
                total_value_at_risk=0.0,
                items=[],
                notes=["No batches expire within the requested window."],
            )

        medicine_ids = sorted({batch.medicine_id for batch in batches})

        demand_units = self.repository.recent_demand(
            as_of=reference,
            lookback_days=self.config.demand_lookback_days,
            medicine_ids=medicine_ids,
        )
        ever_sold = self.repository.medicines_with_any_sales(medicine_ids)

        items = self._assess_batches(batches, demand_units, reference)
        notes = self._build_notes(batches, demand_units, ever_sold)

        # Rank before filtering and limiting, so "top 5" means the five most urgent
        # overall rather than the first five the database happened to return.
        items.sort(key=_ranking_key)

        if query.risk_level is not None:
            items = [item for item in items if item.risk_level is query.risk_level]

        at_risk = [item for item in items if item.potential_excess > 0]

        report = ExpiryRiskReport(
            generated_for=reference,
            window_days=query.window_days,
            demand_lookback_days=self.config.demand_lookback_days,
            total_batches_reviewed=len(batches),
            total_at_risk=len(at_risk),
            total_value_at_risk=round(
                sum(item.value_at_risk for item in at_risk), 2
            ),
            items=items[: query.limit],
            notes=notes,
        )

        logger.info(
            "expiry_risk_assessed",
            extra={
                "batches_reviewed": report.total_batches_reviewed,
                "at_risk": report.total_at_risk,
                "window_days": query.window_days,
            },
        )

        return report

    # -- per-medicine FEFO allocation -----------------------------------

    def _assess_batches(
        self,
        batches: list[BatchStock],
        demand_units: dict[int, int],
        reference: date,
    ) -> list[ExpiryRiskItem]:
        """Assess every batch, allocating each medicine's demand in FEFO order."""

        items: list[ExpiryRiskItem] = []

        # The repository ordered by (medicine_id, expiry_date, batch_id), so grouping
        # is a single pass and each group is already in FEFO order.
        by_medicine: dict[int, list[BatchStock]] = {}
        for batch in batches:
            by_medicine.setdefault(batch.medicine_id, []).append(batch)

        for medicine_id, medicine_batches in by_medicine.items():
            daily_demand = self._daily_demand(demand_units.get(medicine_id, 0))

            # Units of this medicine already spoken for by earlier-expiring batches.
            claimed = 0

            for batch in medicine_batches:
                days = (batch.expiry_date - reference).days

                # Expired stock cannot sell at all, whatever the demand. It also must
                # not consume demand that a live batch could still use.
                if days < 0:
                    expected_sold = 0
                else:
                    # Total demand between now and this batch's expiry, minus what the
                    # batches ahead of it in the FEFO queue will already have taken.
                    demand_by_expiry = daily_demand * days
                    available = max(0.0, demand_by_expiry - claimed)
                    expected_sold = min(max(batch.quantity, 0), int(available))
                    claimed += expected_sold

                items.append(
                    self._build_item(batch, days, expected_sold, daily_demand)
                )

        return items

    def _daily_demand(self, units_in_lookback: int) -> float:
        """Average units sold per day over the lookback window."""

        return max(0.0, units_in_lookback / self.config.demand_lookback_days)

    # -- one batch ------------------------------------------------------

    def _build_item(
        self,
        batch: BatchStock,
        days_to_expiry: int,
        estimated_demand: int,
        daily_demand: float,
    ) -> ExpiryRiskItem:
        # Negative stock is a data defect (no CHECK constraint exists). Treat it as
        # nothing at risk rather than a negative write-off, and let the note flag it.
        sellable = max(batch.quantity, 0)
        excess = max(0, sellable - estimated_demand)

        unit_cost = float(batch.cost_price or Decimal("0"))
        value_at_risk = round(excess * unit_cost, 2)

        level = self._risk_level(days_to_expiry, excess)
        reasons = self._reasons(
            batch, days_to_expiry, estimated_demand, excess, daily_demand, value_at_risk
        )

        return ExpiryRiskItem(
            batch_id=batch.batch_id,
            batch_number=batch.batch_number,
            medicine_id=batch.medicine_id,
            medicine_name=batch.medicine_name,
            expiry_date=batch.expiry_date,
            days_to_expiry=days_to_expiry,
            stock_quantity=batch.quantity,
            estimated_demand=estimated_demand,
            potential_excess=excess,
            unit_cost=unit_cost,
            value_at_risk=value_at_risk,
            risk_level=level,
            priority_score=_priority_score(value_at_risk, days_to_expiry),
            reasons=reasons,
            recommendation=_recommendation(level, excess, days_to_expiry),
        )

    def _risk_level(self, days_to_expiry: int, excess: int) -> RiskLevel:
        """Classify a batch. Deterministic, and driven by excess rather than date.

        Excess is the gate: a batch expiring tomorrow that will sell out tomorrow is
        not a risk, and flagging it would train the pharmacist to ignore the report.
        Once there IS excess, time decides how urgent it is.
        """

        if days_to_expiry < 0:
            return RiskLevel.EXPIRED

        if excess <= 0:
            return RiskLevel.LOW

        if days_to_expiry <= self.config.critical_days:
            return RiskLevel.CRITICAL

        if days_to_expiry <= self.config.warning_days:
            return RiskLevel.HIGH

        if days_to_expiry <= self.config.horizon_days:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW

    def _reasons(
        self,
        batch: BatchStock,
        days: int,
        demand: int,
        excess: int,
        daily_demand: float,
        value_at_risk: float,
    ) -> list[str]:
        """Why this batch got this level, in the pharmacist's terms."""

        if days < 0:
            reasons = [f"expired {abs(days)} day(s) ago"]
        else:
            reasons = [f"{days} day(s) to expiry"]

        if batch.quantity < 0:
            reasons.append(
                f"stock is recorded as {batch.quantity}, which should not be possible "
                "- treated as zero and worth investigating"
            )
            return reasons

        reasons.append(f"{batch.quantity} unit(s) in stock")

        if days < 0:
            reasons.append("expired stock cannot be sold")
        elif daily_demand <= 0:
            reasons.append("no recent sales, so none of it is expected to sell")
        else:
            reasons.append(
                f"selling about {daily_demand:.2f} unit(s)/day, so roughly "
                f"{demand} unit(s) expected to sell before expiry"
            )

        if excess > 0:
            reasons.append(f"estimated excess of {excess} unit(s)")
            reasons.append(f"value at risk {value_at_risk:.2f}")
        else:
            reasons.append("current demand should clear this batch in time")

        return reasons

    def _build_notes(
        self,
        batches: list[BatchStock],
        demand_units: dict[int, int],
        ever_sold: set[int],
    ) -> list[str]:
        """Caveats the analyst must pass on rather than paper over."""

        notes: list[str] = []

        never_sold = sorted(
            {
                batch.medicine_name
                for batch in batches
                if batch.medicine_id not in ever_sold
            }
        )
        if never_sold:
            notes.append(
                "No sales history at all for: "
                + ", ".join(never_sold)
                + ". Their demand estimate is zero because nothing is known, not "
                "because demand is known to be zero."
            )

        no_recent = sorted(
            {
                batch.medicine_name
                for batch in batches
                if batch.medicine_id in ever_sold
                and demand_units.get(batch.medicine_id, 0) == 0
            }
        )
        if no_recent:
            notes.append(
                "Sold in the past but nothing in the last "
                f"{self.config.demand_lookback_days} days: "
                + ", ".join(no_recent)
                + "."
            )

        negative_stock = sorted(
            {batch.batch_number for batch in batches if batch.quantity < 0}
        )
        if negative_stock:
            notes.append(
                "Negative stock recorded for batch(es): "
                + ", ".join(negative_stock)
                + ". This is a data problem, not an expiry problem."
            )

        notes.append(
            f"Demand is the average over the last {self.config.demand_lookback_days} "
            "days projected forward at a flat rate. It is an estimate from history, "
            "not a forecast."
        )

        return notes


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def _priority_score(value_at_risk: float, days_to_expiry: int) -> float:
    """Money at risk per remaining day — how fast this batch is losing value.

    Chosen because it is explainable in one sentence and it balances the two things
    that matter: 10,000 expiring in 60 days is less urgent than 2,000 expiring in 3.
    Ranking purely by value would bury the urgent small loss; ranking purely by date
    would put a 20-rupee batch above a 20,000-rupee one.

    Already-expired stock divides by 1, so it scores its full value and sorts to the
    top, which is right — it is realised loss, not risk.
    """

    return round(value_at_risk / max(days_to_expiry, 1), 2)


def _ranking_key(item: ExpiryRiskItem) -> tuple:
    """Total ordering, so the same data always ranks the same way.

    Severity first because a pharmacist scans by urgency, then the score, then value,
    then the soonest date. ``batch_id`` last makes it total: without it, two identical
    batches could swap places between runs and the report would look unstable.
    """

    return (
        RISK_ORDER[item.risk_level],
        -item.priority_score,
        -item.value_at_risk,
        item.days_to_expiry,
        item.batch_id,
    )


# ---------------------------------------------------------------------------
# Recommendations — advisory text only, nothing is executed
# ---------------------------------------------------------------------------


def _recommendation(level: RiskLevel, excess: int, days: int) -> str:
    """A suggested action for the pharmacist to take, or not.

    The agent never acts. It does not change prices, raise purchase orders, contact
    suppliers or move stock — it says what a person might want to do, and a person
    decides.
    """

    if level is RiskLevel.EXPIRED:
        return (
            "Already expired - quarantine and write off, and check why it was not "
            "caught earlier."
        )

    if excess <= 0:
        return "No action needed; current demand should clear this batch in time."

    if level is RiskLevel.CRITICAL:
        return (
            f"Act now - only {days} day(s) left. Consider a discount or bundle to move "
            "it, and check whether the supplier will take it back."
        )

    if level is RiskLevel.HIGH:
        return (
            "Prioritise this stock for sale, and pause reordering this medicine until "
            "the batch clears."
        )

    return (
        "Watch this one. Review the reorder quantity for this medicine - the excess "
        "suggests it is being bought faster than it sells."
    )
