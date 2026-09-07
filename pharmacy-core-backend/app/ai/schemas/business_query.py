"""The structured query: the only thing the LLM is allowed to say about data access.

THE CONTRACT
------------
    natural language
        -> LLM produces a BusinessQuery          (interpretation)
        -> Pydantic validates it                 (rejection of nonsense)
        -> the period resolves to real dates     (deterministic, in code)
        -> the repository builds SQL from it     (allowlisted columns only)
        -> the LLM explains the returned rows    (no arithmetic)

The model names *what* it wants. It never writes SQL, never picks a table or column,
never computes a date, and never produces a number. Every field below is a closed
enum or a bounded integer, so the widest thing a compromised or confused model can
express is a differently-shaped question — never a different query language.

WHY ENUMS AND NOT STRINGS
-------------------------
A free-text ``dimension`` would eventually reach a SQL builder, and the only thing
standing between "group by product" and "group by (select ...)" would be a blocklist.
Enums invert that: anything not explicitly listed cannot be represented at all, and
Pydantic rejects it before any of our code runs.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.core.time_range import DateRange, Period, resolve_period

# A breakdown is for a person to read. Beyond a screenful it is a data export, which
# is a different feature with different performance characteristics.
MAX_LIMIT = 100
DEFAULT_LIMIT = 10


class Metric(StrEnum):
    """What is being measured. One per repository capability that exists."""

    SALES = "sales"
    PURCHASES = "purchases"
    RETURNS = "returns"
    EXPIRY = "expiry"
    MARGIN = "margin"


class Dimension(StrEnum):
    """What to break the metric down by.

    Every member maps to a column that genuinely exists. Notably **absent**:
    ``CATEGORY``. Medicines have ``name``, ``manufacturer``, ``hsn_code`` and ``mrp``
    — there is no category column, so "sales by category" is unanswerable. Adding the
    member without the column would let the planner promise an answer the repository
    cannot produce, which is worse than saying no.
    """

    PRODUCT = "product"
    MANUFACTURER = "manufacturer"
    SUPPLIER = "supplier"
    DAY = "day"
    MONTH = "month"


class SortDirection(StrEnum):
    DESC = "desc"
    ASC = "asc"


# Which breakdowns each metric can actually serve, given the schema.
#
#   SALES has no SUPPLIER: a sale is linked to a batch, and a batch is not linked to
#   the purchase that created it, so there is no join from a sale to a supplier.
#   MARGIN and EXPIRY have no time dimension: margin is per sold line and expiry is a
#   property of stock on hand; bucketing either by day answers a question nobody asked.
SUPPORTED_DIMENSIONS: dict[Metric, frozenset[Dimension]] = {
    Metric.SALES: frozenset(
        {Dimension.PRODUCT, Dimension.MANUFACTURER, Dimension.DAY, Dimension.MONTH}
    ),
    Metric.PURCHASES: frozenset(
        {Dimension.SUPPLIER, Dimension.DAY, Dimension.MONTH}
    ),
    Metric.RETURNS: frozenset(
        {Dimension.PRODUCT, Dimension.MANUFACTURER, Dimension.DAY, Dimension.MONTH}
    ),
    Metric.MARGIN: frozenset({Dimension.PRODUCT, Dimension.MANUFACTURER}),
    Metric.EXPIRY: frozenset({Dimension.PRODUCT, Dimension.MANUFACTURER}),
}

# EXPIRY measures stock that has *already* expired — a snapshot of now, not a span of
# transactions. "Expired stock last month" has no agreed meaning, and inventing one
# would be a silent lie. Batches *approaching* expiry are the Expiry-Risk agent's job.
METRICS_WITHOUT_PERIOD_SUPPORT = frozenset({Metric.EXPIRY})


class BusinessQuery(BaseModel):
    """One validated request for business data."""

    metric: Metric = Field(description="Which business measure the question is about.")

    dimension: Dimension | None = Field(
        default=None,
        description=(
            "Break the metric down by this. Omit for a single overall total. "
            "Use 'product' for questions like 'which medicine sold the most'."
        ),
    )

    period: Period = Field(
        default=Period.ALL_TIME,
        description=(
            "The time window. Name the period; never compute dates yourself. "
            "Use 'all_time' when the question mentions no time at all."
        ),
    )

    start_date: date | None = Field(
        default=None, description="Only with period='custom'."
    )
    end_date: date | None = Field(
        default=None, description="Only with period='custom'."
    )

    sort: SortDirection = Field(
        default=SortDirection.DESC,
        description="Order of a breakdown. 'desc' for top/most, 'asc' for lowest/least.",
    )

    limit: int = Field(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description=f"Rows in a breakdown, 1-{MAX_LIMIT}.",
    )

    # -- validation ---------------------------------------------------------

    @model_validator(mode="after")
    def _validate(self) -> "BusinessQuery":
        if self.period is Period.CUSTOM:
            if self.start_date is None or self.end_date is None:
                raise ValueError(
                    "period='custom' requires both start_date and end_date"
                )
            if self.start_date > self.end_date:
                raise ValueError(
                    f"start_date {self.start_date} is after end_date {self.end_date}"
                )
        elif self.start_date is not None or self.end_date is not None:
            # Explicit dates alongside a named period is ambiguous: which wins? Reject
            # rather than pick, so a confused planner produces an error instead of a
            # plausible answer to a different question.
            raise ValueError(
                "start_date/end_date are only valid with period='custom'; "
                f"got period={self.period.value!r}"
            )

        if self.dimension is not None:
            allowed = SUPPORTED_DIMENSIONS[self.metric]
            if self.dimension not in allowed:
                raise ValueError(
                    f"metric={self.metric.value!r} cannot be broken down by "
                    f"{self.dimension.value!r}. Supported: "
                    f"{sorted(d.value for d in allowed)}"
                )

        if (
            self.metric in METRICS_WITHOUT_PERIOD_SUPPORT
            and self.period is not Period.ALL_TIME
        ):
            raise ValueError(
                f"metric={self.metric.value!r} reports stock as it stands now and "
                "does not support a time period; use period='all_time'"
            )

        return self

    # -- derived ------------------------------------------------------------

    def date_range(self, *, as_of: date | None = None) -> DateRange:
        """Resolve this query's period into concrete dates."""

        return resolve_period(
            self.period,
            as_of=as_of,
            start_date=self.start_date,
            end_date=self.end_date,
        )

    def key(self) -> str:
        """A stable, readable identifier used to key results and label logs.

        Two different questions must not collide onto one key, or the second result
        would overwrite the first in the metrics dict.
        """

        parts = [self.metric.value]
        if self.dimension:
            parts.append(f"by_{self.dimension.value}")
        if self.period is not Period.ALL_TIME:
            parts.append(self.period.value)
        if self.period is Period.CUSTOM:
            parts.append(f"{self.start_date}_{self.end_date}")
        return "_".join(parts)

    def describe(self) -> str:
        """A human-readable summary, safe to log — shape only, never row content."""

        text = self.metric.value
        if self.dimension:
            text += f" by {self.dimension.value} (top {self.limit}, {self.sort.value})"
        text += f" over {self.period.value}"
        return text


class PlannerOutput(BaseModel):
    """What the planner returns: the queries needed to answer the question.

    An **empty list is a valid, deliberate answer** — it is how the planner says the
    question is not about pharmacy business data at all.
    """

    queries: list[BusinessQuery] = Field(
        default_factory=list,
        description=(
            "The business data needed to answer the question. Empty if the question "
            "is not about the pharmacy's business data."
        ),
    )
