"""Structured output schema for the Business Intelligence Agent."""

from pydantic import BaseModel, Field


class BusinessInsight(BaseModel):
    """Single business insight."""

    title: str = Field(
        description="Short title of the insight.",
    )

    description: str = Field(
        description="Detailed explanation of the insight.",
    )


class BusinessAnalysis(BaseModel):
    """Structured analysis returned by the LLM."""

    summary: str = Field(
        description="Overall business summary.",
    )

    key_insights: list[BusinessInsight] = Field(
        description="Important business insights.",
    )

    recommendations: list[str] = Field(
        description="Recommended business actions.",
    )

    confidence: float = Field(
        ge=0,
        le=1,
        description="Confidence score between 0 and 1.",
    )