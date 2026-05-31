"""The "clipboard" state for the billing graph.

Every node reads some fields and writes others. By declaring this as a TypedDict:
- IDE autocompletes every field
- Type checkers (mypy, pyright) catch typos before runtime
- A new contributor can see every piece of data the graph ever holds, here.

`total=False` means each node only sets the fields it OWNS; fields not yet
populated remain absent (vs. None). Avoids "is this field None because nothing
set it, or None because it was deliberately set to None" ambiguity.
"""
from typing import TypedDict


class BillingState(TypedDict, total=False):
    """State passed between every node in the billing graph.

    Lifecycle (populated progressively as the request flows):

        INPUT                       pharmacist_input
        ↓ extract_intent (LLM)      extracted_intent
        ↓ resolve_medicine (DB)     medicine_id
        ↓ select_batch (DB FEFO)    batch_id
        ↓ compute_pricing           total_amount
        ↓ persist_sale (DB tx)      sale_id
        OUTPUT                      sale_id + total_amount returned to caller
    """

    # ----- Input — set by the API endpoint before invoking the graph -----
    pharmacist_input: str  # raw text typed or transcribed from voice

    # ----- Filled by extract_intent (LLM call) -----
    # In step 3.2 this gets a stronger type via Pydantic (ExtractedIntent schema).
    # For now we keep it as dict to keep the contract simple.
    extracted_intent: dict

    # ----- Filled by resolve_medicine — the matched DB row's id -----
    medicine_id: int

    # ----- Filled by select_batch — FEFO winner from Phase 2's select_fefo -----
    batch_id: int

    # ----- Filled by compute_pricing -----
    total_amount: float

    # ----- Filled by persist_sale — the new invoice id -----
    sale_id: int

    # ----- Cross-cutting: accumulated soft errors a node can report without aborting -----
    errors: list[str]
