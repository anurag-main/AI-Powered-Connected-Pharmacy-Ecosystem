"""The structured request for expiry-risk analysis, and the shape of its answer.

Same contract as ``business_query``: the LLM names what it wants, every field is a
closed enum or a bounded integer, and nothing the model can produce reaches SQL as
text. The model cannot ask for a column, a table, an operator or an unbounded scan.

The *answer* types live here too, because they are the thing the LLM is handed and
must not alter. Every number in :class:`ExpiryRiskItem` was computed in Python or SQL;
the analyzer's job is to explain them, never to recompute or round them.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

# A year ahead is already beyond any useful action window, and the query is a
# report for a person to read, not a data export.
MAX_WINDOW_DAYS = 365
MAX_LIMIT = 100
DEFAULT_LIMIT = 10


class RiskLevel(StrEnum):
    """How urgent a batch is. Ordered worst-first in :data:`RISK_ORDER`."""

    EXPIRED = "expired"
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Explicit ordering, so sorting never depends on how the enum happens to be declared.
RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.EXPIRED: 0,
    RiskLevel.CRITICAL: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.MEDIUM: 3,
    RiskLevel.LOW: 4,
}


class ExpiryRiskQuery(BaseModel):
    """One validated request for expiry-risk analysis."""

    window_days: int = Field(
        default=90,
        ge=1,
        le=MAX_WINDOW_DAYS,
        description=(
            "Look at batches expiring within this many days. 30 for 'this month', "
            "7 for 'this week'. Default 90 covers the usual planning horizon."
        ),
    )

    risk_level: RiskLevel | None = Field(
        default=None,
        description=(
            "Return only batches at this risk level. Omit for everything in the "
            "window. Use 'critical' for questions about urgent or serious risk."
        ),
    )

    include_expired: bool = Field(
        default=True,
        description=(
            "Include stock that has ALREADY expired. That is realised loss rather "
            "than risk, but a pharmacist asking about expiry usually wants to see it."
        ),
    )

    medicine_id: int | None = Field(
        default=None,
        ge=1,
        description="Restrict to one medicine, when the question names a specific one.",
    )

    limit: int = Field(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description=f"Number of batches to return, highest priority first. 1-{MAX_LIMIT}.",
    )

    def describe(self) -> str:
        """A log-safe summary: shape of the request, never its results."""

        parts = [f"window={self.window_days}d"]
        if self.risk_level:
            parts.append(f"risk={self.risk_level.value}")
        if self.medicine_id:
            parts.append(f"medicine={self.medicine_id}")
        if not self.include_expired:
            parts.append("excluding expired")
        parts.append(f"top {self.limit}")
        return " ".join(parts)


class ExpiryRiskItem(BaseModel):
    """One batch's risk assessment. Every field is computed, none is generated.

    The analyzer receives these verbatim and must quote them unchanged.
    """

    batch_id: int
    batch_number: str
    medicine_id: int
    medicine_name: str

    expiry_date: date
    days_to_expiry: int = Field(
        description="Negative when the batch has already expired."
    )

    stock_quantity: int
    estimated_demand: int = Field(
        description=(
            "Units of THIS batch expected to sell before it expires, from recent "
            "sales and FEFO ordering. An estimate from history, not a forecast."
        )
    )
    potential_excess: int = Field(
        description="stock_quantity - estimated_demand, floored at zero."
    )

    unit_cost: float
    value_at_risk: float = Field(
        description="potential_excess x unit_cost — the money likely to be written off."
    )

    risk_level: RiskLevel
    priority_score: float = Field(
        description="Value at risk per remaining day. Higher means act sooner."
    )
    reasons: list[str] = Field(
        description="Plain-language explanation of why this level was assigned."
    )
    recommendation: str = Field(
        description="Suggested action. Advisory only — nothing is executed."
    )


class ExpiryRiskReport(BaseModel):
    """The full deterministic result handed to the LLM."""

    generated_for: date = Field(description="The date risk was assessed against.")
    window_days: int
    demand_lookback_days: int

    total_batches_reviewed: int
    total_at_risk: int = Field(
        description="Batches with a non-zero potential excess."
    )
    total_value_at_risk: float

    items: list[ExpiryRiskItem]

    counts_by_risk: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "How many batches sit at each risk level, counted BEFORE the limit is "
            "applied. A dashboard cannot derive these from `items` — asking for the "
            "top 5 would make every count at most 5."
        ),
    )

    notes: list[str] = Field(
        default_factory=list,
        description=(
            "Caveats the analyst must pass on — e.g. that a medicine has no sales "
            "history, so its demand estimate is zero rather than unknown."
        ),
    )
