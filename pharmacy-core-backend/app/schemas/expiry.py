"""HTTP request/response schemas for the Expiry Risk Agent."""

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
