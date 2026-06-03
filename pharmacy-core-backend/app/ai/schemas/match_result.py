"""Pydantic schemas for the catalog-match confirm step.

After fuzzy search produces a short list of candidate catalog medicines for each
spoken (possibly mis-heard) name, the LLM picks the best one. These schemas are
the structured output it must return.
"""
from typing import Optional

from pydantic import BaseModel, Field


class MatchDecision(BaseModel):
    """The LLM's verdict for ONE spoken item."""

    spoken: str = Field(..., description="The spoken item name being matched, copied verbatim")
    chosen: Optional[str] = Field(
        None,
        description="The EXACT catalog medicine name that best matches, copied from the "
        "candidate list. null if none of the candidates is plausibly the same medicine.",
    )
    confidence: str = Field(
        ...,
        description="'high' if confident the chosen medicine is correct, else 'low'",
    )


class MatchResult(BaseModel):
    """One MatchDecision per spoken item sent for confirmation."""

    matches: list[MatchDecision] = Field(..., description="One entry per spoken item")
