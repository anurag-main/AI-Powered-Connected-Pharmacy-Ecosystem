"""Structured output schema for long-term memory extraction."""

from pydantic import BaseModel, Field


class MemoryFact(BaseModel):
    """
    A single durable fact extracted from a conversation.
    """

    fact: str = Field(
        description=(
            "A durable fact that should be remembered "
            "for future conversations."
        )
    )

    category: str = Field(
        description=(
            "The category of the memory."
        )
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence that this fact is worth storing."
        ),
    )


class MemoryExtraction(BaseModel):
    """
    Structured output returned by the Memory Extractor.
    """

    memories: list[MemoryFact] = Field(
        default_factory=list,
        description=(
            "List of durable memories extracted "
            "from the conversation."
        ),
    )