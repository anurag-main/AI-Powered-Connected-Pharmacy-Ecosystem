"""Structured output schema for the Inventory Risk analyst."""

from pydantic import BaseModel, Field


class InventoryAnalysis(BaseModel):
    """What the analyst node returns."""

    summary: str = Field(
        description=(
            "Plain-language explanation for the pharmacy owner, several sentences "
            "long. It MUST name the specific medicines that matter and give each "
            "one's figures from the report - stock, days of cover, capital at risk - "
            "and why it was classified that way. A summary that quotes only totals "
            "and names no medicine is not an acceptable answer: the owner cannot act "
            "on a total. End with what they should review."
        )
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How well the underlying data supports this answer. Lower it when the "
            "report notes unknown stock age, negative quantities, or medicines with "
            "no sales history."
        ),
    )
