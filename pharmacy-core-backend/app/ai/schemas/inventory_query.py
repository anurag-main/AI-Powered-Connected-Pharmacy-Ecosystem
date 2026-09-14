"""The structured request for inventory-risk analysis, and the shape of its answer.

Same contract as ``expiry_query`` and ``business_query``: the LLM names what it
wants, every field is a closed enum or a bounded number, and nothing the model can
produce reaches SQL as text. The model cannot ask for a column, a table, an operator
or an unbounded scan.

The *answer* types live here too, because they are the thing the LLM is handed and
must not alter. Every number in :class:`InventoryRiskItem` was computed in Python or
SQL by ``InventoryRiskService``; the analyzer's job is to explain them, never to
recompute or round them.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

MAX_LIMIT = 100
DEFAULT_LIMIT = 10

# A week is the shortest target cover that is not just "today's stock", and a year is
# already past the point where holding more is a decision rather than a buffer.
MIN_TARGET_COVER_DAYS = 7
MAX_TARGET_COVER_DAYS = 365


class InventoryRiskLevel(StrEnum):
    """How badly a medicine's capital is misallocated.

    Named ``InventoryRiskLevel`` and not ``RiskLevel`` on purpose: the expiry agent
    already owns a ``RiskLevel`` with different members, and two enums of the same
    name meaning different things is a bug waiting for an import to be tidied up.
    """

    DEAD = "dead"
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    HEALTHY = "healthy"


# Explicit ordering, so sorting never depends on how the enum happens to be declared.
RISK_ORDER: dict[InventoryRiskLevel, int] = {
    InventoryRiskLevel.DEAD: 0,
    InventoryRiskLevel.CRITICAL: 1,
    InventoryRiskLevel.HIGH: 2,
    InventoryRiskLevel.MEDIUM: 3,
    InventoryRiskLevel.HEALTHY: 4,
}


class InventorySort(StrEnum):
    """How to order the returned medicines.

    A closed set, because it maps to a fixed sort key in Python. An open string would
    put a column name in the model's hands, which is the thing this contract exists to
    prevent.
    """

    #: Worst risk level first, then most capital. The default.
    RISK = "risk"
    #: Most money trapped first, whatever the level.
    CAPITAL = "capital_at_risk"
    #: Longest cover first. Medicines with no cover figure sort last.
    COVER = "days_of_cover"
    #: Oldest stock first. Medicines with no known age sort last.
    STOCK_AGE = "stock_age"


class InventoryRiskQuery(BaseModel):
    """One validated request for inventory-risk analysis."""

    target_cover_days: int = Field(
        default=60,
        ge=MIN_TARGET_COVER_DAYS,
        le=MAX_TARGET_COVER_DAYS,
        description=(
            "How many days of stock the pharmacy wants to hold. Anything above this "
            "counts as excess. Default 60 — a normal two-month reorder cycle. "
            "Lowering it makes more stock count as excess."
        ),
    )

    risk_level: InventoryRiskLevel | None = Field(
        default=None,
        description=(
            "Return only medicines at this risk level. Omit for everything. Use "
            "'dead' for questions about dead or non-moving stock, 'critical' for the "
            "worst overstock."
        ),
    )

    min_capital_at_risk: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Return only medicines with at least this much money at risk, in rupees. "
            "Use when the question asks about significant or material amounts."
        ),
    )

    medicine_id: int | None = Field(
        default=None,
        ge=1,
        description="Restrict to one medicine, when the question names a specific id.",
    )

    sort: InventorySort = Field(
        default=InventorySort.RISK,
        description=(
            "Ordering. 'risk' is worst level first then most money, and is right for "
            "almost every question. 'capital_at_risk' for 'where is the most money', "
            "'days_of_cover' for 'what do I have most of', 'stock_age' for 'what has "
            "sat longest'."
        ),
    )

    limit: int = Field(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description=f"Number of medicines to return, best match first. 1-{MAX_LIMIT}.",
    )

    def describe(self) -> str:
        """A log-safe summary: shape of the request, never its results."""

        parts = [f"target={self.target_cover_days}d"]
        if self.risk_level:
            parts.append(f"risk={self.risk_level.value}")
        if self.min_capital_at_risk > 0:
            parts.append(f"min capital Rs {self.min_capital_at_risk:,.0f}")
        if self.medicine_id:
            parts.append(f"medicine={self.medicine_id}")
        parts.append(f"sorted by {self.sort.value}")
        parts.append(f"top {self.limit}")
        return " ".join(parts)


class InventoryRiskItem(BaseModel):
    """One medicine's inventory-risk position. Every field is computed, none generated.

    The grain is **per medicine**, not per batch. Velocity is only knowable per
    medicine, the decision a pharmacist takes ("stop reordering this") is per
    medicine, and the per-batch view already exists in the expiry agent.

    The analyzer receives these verbatim and must quote them unchanged.
    """

    medicine_id: int
    medicine_name: str

    stock_quantity: int = Field(
        description="Every unit on the shelf, sellable or not. The capital view."
    )
    inventory_value: float = Field(
        description="stock_quantity valued at batch cost — money currently tied up."
    )
    sellable_quantity: int = Field(
        description="Units that can still be dispensed. The cover view."
    )
    weighted_avg_cost: float = Field(
        description=(
            "Value per unit across all of this medicine's batches. Weighted, because "
            "batches are routinely bought at different prices."
        )
    )

    units_sold: int = Field(description="Units sold across the demand window.")
    daily_velocity: float = Field(
        description="units_sold / lookback days. An average from history, not a forecast."
    )
    days_of_cover: float | None = Field(
        description=(
            "sellable_quantity / daily_velocity. NULL when nothing is selling — that "
            "is not infinity, it means there is no rate to divide by."
        )
    )

    last_sale_date: date | None = Field(description="Most recent sale. NULL if never sold.")
    days_since_last_sale: int | None = None
    ever_sold: bool = Field(
        description="False means no sales history at all — a different state from slow."
    )

    target_stock: int = Field(description="What the shop should hold at this velocity.")
    excess_units: int = Field(description="sellable_quantity - target_stock, floored at 0.")
    excess_value: float = Field(description="excess_units x weighted_avg_cost.")

    capital_at_risk: float = Field(
        description=(
            "Money this medicine is absorbing that it should not be. The full "
            "inventory value for dead stock, the excess otherwise — because stock "
            "inside the target is capital doing its job."
        )
    )

    oldest_receipt_date: date | None = None
    stock_age_days: int | None = Field(
        default=None,
        description=(
            "Days since the oldest still-held batch was received. NULL means unknown, "
            "never zero — some batches predate purchase tracking."
        ),
    )

    risk_level: InventoryRiskLevel
    risk_reasons: list[str] = Field(
        default_factory=list,
        description="Plain facts that produced the level. Each checkable against the fields above.",
    )


class InventoryRiskReport(BaseModel):
    """The full deterministic result handed to the LLM."""

    generated_for: date = Field(description="The date risk was assessed against.")
    demand_lookback_days: int
    target_cover_days: int

    medicines_reviewed: int = Field(
        description="Medicines holding stock. Counted BEFORE any filter or limit."
    )
    medicines_without_stock: int = Field(
        description="Medicines that exist but hold nothing. No capital, so no risk."
    )
    items_matching_filter: int = Field(
        default=0,
        description=(
            "How many medicines matched the filter, before `limit`. Lets a caller say "
            "'showing 10 of 84' instead of implying 10 is the whole answer."
        ),
    )

    total_inventory_value: float = Field(
        description="Every stocked medicine's value. A shop-level figure, not filtered."
    )
    total_capital_at_risk: float = Field(
        description="Every stocked medicine's capital at risk. Also not filtered."
    )
    capital_at_risk_in_view: float = Field(
        default=0.0,
        description=(
            "Capital at risk across the medicines matching the filter, before "
            "`limit`. Exists so nobody has to add up `items` to answer 'how much do "
            "these account for' - and so the LLM, which must not do arithmetic, has "
            "the figure handed to it."
        ),
    )

    items: list[InventoryRiskItem]

    counts_by_risk: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Medicines at each risk level, counted over the WHOLE shop before any "
            "filter or limit. A dashboard cannot derive these from `items` — asking "
            "for the top 5 dead items would make every count at most 5."
        ),
    )

    notes: list[str] = Field(
        default_factory=list,
        description=(
            "Caveats the analyst must pass on — e.g. that some stock has no purchase "
            "record, so its age is unknown rather than zero."
        ),
    )
