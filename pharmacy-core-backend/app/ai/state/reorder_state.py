"""The "clipboard" state for the reorder graph.

Same idea as BillingState: a TypedDict that travels node → node. Each node
reads some keys and writes others. `total=False` means a node only sets the
keys it OWNS.

Lifecycle:
    INPUT                         (empty {} — the agent pulls its own data)
    ↓ fetch_candidates (DB)       candidates
    ↓ decide_reorders             proposals
    OUTPUT                        proposals returned to caller
"""
from operator import add
from typing import Annotated, TypedDict


class ReorderState(TypedDict, total=False):
    """State passed between the reorder graph's nodes."""

    # ----- Filled by fetch_candidates — every medicine's raw numbers -----
    # [{"medicine_id": 1, "name": "Crocin 500mg", "current_stock": 3, "daily_velocity": 2.0}, ...]
    candidates: list[dict]

    # ----- Filled by decide_reorders — only the medicines that need ordering -----
    # [{...candidate, "days_of_cover": 1.5, "reorder_qty": 10}, ...]
    proposals: list[dict]

    # ----- Cross-cutting soft errors (same reducer pattern as BillingState) -----
    # Annotated[..., add] = CONCATENATE each node's errors instead of overwriting.
    errors: Annotated[list[str], add]
