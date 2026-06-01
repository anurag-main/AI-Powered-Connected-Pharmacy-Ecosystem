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
        ↓ select_batch (DB FEFO)    batched_items      ← step 3.4
        ↓ compute_pricing           priced_items + total_amount   ← step 3.5
        ↓ persist_sale (DB tx)      sale_id            ← step 3.7
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

    # ----- Filled by select_batch — each resolved item enriched with the FEFO winner -----
    # Has shape: [
    #   {...resolved_item, "batch_id": 7, "batch_number": "A001", "expiry_date": "2026-02-15"},
    #   ...
    # ]
    # Items with no usable batch (expired / out of stock) are NOT in this list — they're errors.
    batched_items: list[dict]

    # ----- Filled by compute_pricing — adds unit_price + line_total per item -----
    # Has shape: [
    #   {...batched_item, "unit_price": 25.0, "line_total": 50.0},
    #   ...
    # ]
    priced_items: list[dict]

    # ----- Filled by compute_pricing — sum of all line_total -----
    total_amount: float

    # ----- Filled by persist_sale — the new invoice id -----
    sale_id: int

    # ----- Cross-cutting: accumulated soft errors a node can report without aborting -----
    errors: list[str]
