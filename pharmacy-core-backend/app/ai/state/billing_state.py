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
        ↓ resolve_medicine (DB)     resolved_items     ← step 3.3
        ↓ select_batch (DB FEFO)    priced_items       ← step 3.5
        ↓ compute_pricing           total_amount
        ↓ persist_sale (DB tx)      sale_id
        OUTPUT                      sale_id + total_amount returned to caller
    """

    # ----- Input — set by the API endpoint before invoking the graph -----
    pharmacist_input: str  # raw text typed or transcribed from voice

    # ----- Filled by extract_intent (LLM call) -----
    # Has shape: {"items": [...], "customer_name": str|None, "customer_phone": str|None}
    extracted_intent: dict

    # ----- Filled by resolve_medicine — each extracted item enriched with medicine_id -----
    # Has shape: [
    #   {"name": "Crocin 500mg", "quantity": 2, "unit": "strip", "medicine_id": 42},
    #   ...
    # ]
    # If a medicine couldn't be found, it's NOT in this list — it's reported in `errors`.
    resolved_items: list[dict]

    # ----- Filled by select_batch + compute_pricing (step 3.5+) -----
    # Each item gains: batch_id, unit_price, line_total.
    priced_items: list[dict]

    # ----- Filled by compute_pricing -----
    total_amount: float

    # ----- Filled by persist_sale — the new invoice id -----
    sale_id: int

    # ----- Cross-cutting: accumulated soft errors a node can report without aborting -----
    errors: list[str]
