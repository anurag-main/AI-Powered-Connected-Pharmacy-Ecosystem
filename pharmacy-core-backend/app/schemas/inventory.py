"""HTTP request/response schemas for the Inventory Risk Agent."""

from datetime import date

from pydantic import BaseModel, Field

from app.ai.schemas.inventory_query import InventoryRiskItem


class InventoryAnalysisRequest(BaseModel):
    """Request received from the frontend."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural-language question about inventory and capital.",
        examples=["Which medicines are tying up the most capital?"],
    )

    thread_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description=(
            "Conversation id. Send the same value for every turn of a chat to keep "
            "its history; use a new value to start a fresh conversation."
        ),
        examples=["conv-8f3a1c2b"],
    )


class InventoryAnalysisResponse(BaseModel):
    """Response returned to the frontend.

    Carries BOTH the prose and the structured items. The narrative is the model's
    wording; `items` is the deterministic data behind it, so a caller can render a
    table, or check a figure in the text against the number it came from, without
    trusting the prose.
    """

    answer: str
    confidence: float

    medicines_reviewed: int
    total_inventory_value: float
    total_capital_at_risk: float
    items: list[InventoryRiskItem]
    notes: list[str]

    execution_time_ms: int
    agent_version: str


class InventoryReportResponse(BaseModel):
    """The deterministic report, with no LLM anywhere in its production.

    This is what the dashboard renders. It is separate from
    :class:`InventoryAnalysisResponse` because the two answer different questions:
    that one explains a report in prose, this one *is* the report. Keeping them apart
    means the table can load fast and free while the prose is still running.
    """

    generated_for: date
    demand_lookback_days: int
    target_cover_days: int

    medicines_reviewed: int
    medicines_without_stock: int
    items_matching_filter: int = Field(
        description=(
            "Medicines matching the filter before `limit` - so a table can say "
            "showing 10 of 84 rather than implying 10 is the whole answer."
        )
    )

    total_inventory_value: float
    total_capital_at_risk: float
    capital_at_risk_in_view: float = Field(
        description=(
            "Capital at risk across the medicines matching the filter, before "
            "`limit` - so a filtered table can state its own subtotal without the "
            "caller summing rows it may not have all of."
        )
    )

    counts_by_risk: dict[str, int] = Field(
        description=(
            "Medicines at each risk level across the WHOLE shop, before any filter or "
            "limit - so a summary card stays honest while the table is filtered."
        )
    )

    items: list[InventoryRiskItem]
    notes: list[str]

    execution_time_ms: int


class InventoryExplanationResponse(BaseModel):
    """Prose for a report the caller already has.

    Deliberately carries no figures. The dashboard already holds the numbers from
    /report; duplicating them here would create two sources of truth for the same
    screen and invite them to disagree.
    """

    answer: str
    confidence: float
    execution_time_ms: int
    agent_version: str
