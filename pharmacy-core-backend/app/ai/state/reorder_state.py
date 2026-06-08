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
    # [{"medicine_id": 1, "name": "Crocin 500mg", "current_stock": 3,
    #   "daily_velocity": 2.0, "days_since_added": 3}, ...]
    candidates: list[dict]

    # ----- Filled by decide_reorders — 0-sales items it couldn't judge -----
    # Passed to judge_uncertain (the LLM): brand-new product vs dead stock?
    uncertain: list[dict]

    # ----- Reorder proposals — written by BOTH decide_reorders AND judge_uncertain.
    # Annotated[..., add] CONCATENATES both nodes' lists. WITHOUT the reducer,
    # judge_uncertain's return would OVERWRITE decide_reorders' proposals. This is
    # the key LangGraph lesson: a field with two writers needs a reducer.
    proposals: Annotated[list[dict], add]

    # ----- Cross-cutting soft errors (same reducer pattern) -----
    errors: Annotated[list[str], add]
