"""Structured output schema for the Business Reflector."""

from pydantic import BaseModel, Field


class ReflectionOutput(BaseModel):
    """
    Decision produced by the reflection node after
    reviewing the business analysis.
    """

    sufficient: bool = Field(
        ...,
        description="True if enough information exists to answer the question.",
    )

    missing_tasks: list[str] = Field(
        default_factory=list,
        description=(
            "Additional business capabilities required before "
            "another analysis."
        ),
    )

    reason: str = Field(
        ...,
        description="Reason for the reflection decision.",
    )