"""HTTP contract for the Reorder domain.

What the GET /api/v1/reorder/suggestions endpoint returns. The graph's proposals
are loose dicts with extra internal keys (daily_velocity, days_since_added, ...);
this schema picks only the fields the UI needs and IGNORES the rest.
"""
from pydantic import BaseModel, ConfigDict, Field


class ReorderProposal(BaseModel):
    """One suggested reorder the owner will approve/reject."""

    medicine_id: int
    name: str
    current_stock: int
    reorder_qty: int

    # "rule" = decided by deterministic math; "llm" = the judgment node's suggestion.
    source: str = Field("rule", description="'rule' (math) or 'llm' (judgment)")

    # Present on rule-based proposals (finite cover); None on LLM ones.
    days_of_cover: float | None = None

    # Present on LLM proposals — the plain-English why + how sure + review flag.
    reason: str | None = None
    confidence: str | None = None
    needs_review: bool = False

    # Drop the internal keys (daily_velocity, days_since_added) instead of erroring.
    model_config = ConfigDict(extra="ignore")


class ReorderSuggestionsResponse(BaseModel):
    """The full reorder report. An empty `proposals` list is a valid 200 answer."""

    count: int
    proposals: list[ReorderProposal]
    errors: list[str] = []
