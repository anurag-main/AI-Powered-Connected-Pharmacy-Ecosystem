"""Structured output schema for the Business Reflector."""

from pydantic import BaseModel, Field

from app.ai.schemas.business_query import BusinessQuery


class ReflectionOutput(BaseModel):
    """The reflector's verdict on whether the collected data answers the question."""

    sufficient: bool = Field(
        description="True if the collected data is enough to answer the question.",
    )

    missing_queries: list[BusinessQuery] = Field(
        default_factory=list,
        description=(
            "Additional business queries needed before another analysis. Leave empty "
            "when the data is sufficient, or when no available query could help."
        ),
    )

    reason: str = Field(
        description="Why the data is or is not sufficient.",
    )
