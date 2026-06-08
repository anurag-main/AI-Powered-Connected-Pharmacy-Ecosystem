"""LangGraph node — decide_reorders (the night manager — the deterministic brain).

Makes every CLEAR-CUT call with pure math:
    REASON       — days_of_cover vs the reorder point
    PLAN         — suggest_reorder_qty
    SELF-CORRECT — is_qty_sane rejects an absurd number

The one thing it CAN'T judge: a medicine with 0 recent sales. Brand-new product
that hasn't sold yet, or dead stock to stop ordering? No formula answers that, so
those go into state['uncertain'] for the LLM judgment node (judge_uncertain).

Writes:
    state['proposals'] — clear reorder proposals
    state['uncertain'] — 0-sales items that need the LLM's judgment
    state['errors']    — any candidate whose suggested qty failed the sanity net

Analogy (kid-level):
    The night manager handles every obvious row himself. The head-scratchers
    ("this hasn't sold at all — new or dead?") he sets aside as a note for the
    senior pharmacist (the LLM).

v1 limitation: lead time + safety are flat CONSTANTS. Real systems store lead
time per supplier and derive safety stock from demand variability.
"""
from app.ai.state.reorder_state import ReorderState
from app.ai.tools.reorder_tools import days_of_cover, is_qty_sane, suggest_reorder_qty

# Flat v1 assumptions. TODO(real): per-supplier lead time + variance-based safety.
DEFAULT_LEAD_TIME_DAYS = 3
DEFAULT_SAFETY_DAYS = 2


def decide_reorders(state: ReorderState) -> dict:
    """Clear cases -> proposals; 0-sales cases -> uncertain (handed to the LLM)."""

    candidates = state.get("candidates")
    if not candidates:
        return {"errors": ["decide_reorders: no candidates to evaluate"]}

    reorder_point = DEFAULT_LEAD_TIME_DAYS + DEFAULT_SAFETY_DAYS

    proposals: list[dict] = []
    uncertain: list[dict] = []
    errors: list[str] = []

    for c in candidates:
        # 0 recent sales -> math can't tell "brand new" from "dead stock".
        # Hand it to the LLM judgment node instead of guessing.
        if c["daily_velocity"] <= 0:
            uncertain.append(c)
            continue

        cover = days_of_cover(c["current_stock"], c["daily_velocity"])

        # REASON — plenty of cover? confident skip.
        if cover >= reorder_point:
            continue

        # PLAN — how many to order to survive lead time + safety buffer.
        qty = suggest_reorder_qty(
            c["daily_velocity"], DEFAULT_LEAD_TIME_DAYS, DEFAULT_SAFETY_DAYS
        )

        # SELF-CORRECT — reject an absurd number instead of proposing it.
        if not is_qty_sane(qty):
            errors.append(f"decide_reorders: insane qty {qty} for {c['name']!r}")
            continue

        # PROPOSE — a sticky note for the owner. We NEVER auto-buy.
        proposals.append({**c, "days_of_cover": cover, "reorder_qty": qty})

    return {"proposals": proposals, "uncertain": uncertain, "errors": errors}


# ============================================================================
# Smoke test — pure, NO database (we hand-feed fake candidates).
#     python -m app.ai.nodes.decide_reorders
# ============================================================================

if __name__ == "__main__":
    import json

    test_state: ReorderState = {
        "candidates": [
            {"medicine_id": 1, "name": "Crocin 500mg", "current_stock": 3, "daily_velocity": 2.0},   # low -> REORDER
            {"medicine_id": 2, "name": "Dolo 650", "current_stock": 100, "daily_velocity": 1.0},      # plenty -> skip
            {"medicine_id": 3, "name": "Rare Syrup", "current_stock": 1, "daily_velocity": 0.0},      # 0 sales -> uncertain
        ]
    }

    print("========== decide_reorders ==========")
    out = decide_reorders(test_state)
    print("proposals:", json.dumps(out.get("proposals", []), ensure_ascii=False))
    print("uncertain (-> LLM):", [u["name"] for u in out.get("uncertain", [])])
    print("errors:", out.get("errors", []))
    # Expected: ONE proposal (Crocin); Dolo skipped (plenty); Rare Syrup -> uncertain.
