"""HTTP request/response schemas for the Expiry Risk Agent."""

from datetime import date

from pydantic import BaseModel, Field

from app.ai.schemas.expiry_query import ExpiryRiskItem


class ExpiryAnalysisRequest(BaseModel):
    """Request received from the frontend."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural-language question about expiry risk.",
        examples=["Which medicines are expiring soon?"],
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


class ExpiryAnalysisResponse(BaseModel):
    """Response returned to the frontend.

    Carries BOTH the prose and the structured items. The narrative is the model's
    wording; `items` is the deterministic data behind it, so a caller can render a
    table, or check a figure in the text against the number it came from, without
    trusting the prose.
    """

    answer: str
    confidence: float

    total_batches_reviewed: int
    total_at_risk: int
    total_value_at_risk: float
    items: list[ExpiryRiskItem]
    notes: list[str]

    execution_time_ms: int
    agent_version: str


class ExpiryReportResponse(BaseModel):
    """The deterministic report, with no LLM anywhere in its production.

    This is what the dashboard renders. It is separate from
    :class:`ExpiryAnalysisResponse` because the two answer different questions:
    that one explains a report in prose, this one *is* the report. Keeping them
    apart means the table can load fast and free while the prose is still running.
    """

    generated_for: date
    window_days: int
    demand_lookback_days: int

    total_batches_reviewed: int
    total_at_risk: int
    total_value_at_risk: float

    counts_by_risk: dict[str, int] = Field(
        description=(
            "Batches at each risk level, counted before `limit` was applied — so a "
            "summary card can say 12 while the table shows the top 5."
        )
    )

    items: list[ExpiryRiskItem]
    notes: list[str]

    execution_time_ms: int


class ExpiryExplanationResponse(BaseModel):
    """Prose for a report the caller already has.

    Deliberately carries no figures. The dashboard already holds the numbers from
    /report; duplicating them here would create two sources of truth for the same
    screen and invite them to disagree.
    """

    answer: str
    confidence: float
    execution_time_ms: int
    agent_version: str
