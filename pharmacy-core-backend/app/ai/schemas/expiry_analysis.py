"""Structured output schema for the Expiry Risk analyst."""

from pydantic import BaseModel, Field


class ExpiryAnalysis(BaseModel):
    """What the analyst node returns."""

    summary: str = Field(
        description="Plain-language explanation of the expiry risk and what to do."
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How well the underlying data supports this answer. Lower it when the "
            "report notes missing sales history or other data problems."
        ),
    )
