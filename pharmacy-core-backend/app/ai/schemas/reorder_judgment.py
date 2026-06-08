"""Pydantic schema for the LLM's reorder judgment (structured output).

The judgment node sends the LLM the 0-sales medicines + context. The LLM MUST
reply in this exact shape — validated by Pydantic before we act on it. Same
discipline as ExtractedIntent / MatchResult: never act on raw LLM text.
"""
from typing import Optional

from pydantic import BaseModel, Field


class ItemJudgment(BaseModel):
    """The LLM's verdict for ONE 0-sales medicine."""

    medicine_id: int = Field(..., description="The medicine_id being judged, copied from the input")
    action: str = Field(
        ...,
        description="One of: 'reorder' (stock it now), 'watch' (leave it, check later), "
        "'ignore' (dead stock, stop ordering)",
    )
    suggested_qty: Optional[int] = Field(
        None,
        description="Units to order — REQUIRED when action is 'reorder', otherwise null. "
        "Keep it a modest starter quantity.",
    )
    reason: str = Field(..., description="One short plain-English sentence the owner will read")
    confidence: str = Field(..., description="'high' or 'low'")


class ReorderJudgment(BaseModel):
    """One ItemJudgment per uncertain medicine, in the same order sent."""

    judgments: list[ItemJudgment] = Field(..., description="One entry per uncertain medicine")
