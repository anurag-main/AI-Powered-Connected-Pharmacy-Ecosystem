"""LangGraph node — decide_reorders (the night manager — the AGENT'S BRAIN).

For each candidate, decides whether to reorder and how much, then writes a
PROPOSAL (the pharmacist approves it later — we never auto-buy). This is the
node where your 5 agent words finally show up:

    REASON       — days_of_cover vs the reorder point
    PLAN         — suggest_reorder_qty (how many to order)
    SELF-CORRECT — is_qty_sane rejects an absurd number instead of proposing it
    (REMEMBER / human-in-the-loop come when we persist + show proposals)

Writes:
    state['proposals'] — [{...candidate, days_of_cover, reorder_qty}, ...]
    state['errors']    — any candidate whose suggested qty failed the sanity net

Analogy (kid-level):
    The night manager reads each row of the clerk's sheet and asks ONE question:
    "Will we run dry before the supplier restocks?" If yes, he works out how many
    boxes to order, double-checks the number isn't crazy, and writes a sticky note
    for the owner. If there's plenty (or it never sells), he moves on.

v1 limitation (be honest in interviews):
    Lead time + safety are flat CONSTANTS here. Real systems store lead time
    PER SUPPLIER and derive safety stock from demand variability. We ship the
    honest v1 and document the gap.
"""
from app.ai.state.reorder_state import ReorderState
from app.ai.tools.reorder_tools import days_of_cover, is_qty_sane, suggest_reorder_qty

# Flat v1 assumptions. TODO(real): per-supplier lead time + variance-based safety.
DEFAULT_LEAD_TIME_DAYS = 3
DEFAULT_SAFETY_DAYS = 2


def decide_reorders(state: ReorderState) -> dict:
    """Turn raw candidates into reorder proposals (reason → plan → self-correct)."""

    candidates = state.get("candidates")
    if not candidates:
        return {"errors": ["decide_reorders: no candidates to evaluate"]}

    # The trigger line: if cover drops below this many days, we're at risk of
    # running dry before a resupply arrives.
    reorder_point = DEFAULT_LEAD_TIME_DAYS + DEFAULT_SAFETY_DAYS

    proposals: list[dict] = []
    errors: list[str] = []

    for c in candidates:
        cover = days_of_cover(c["current_stock"], c["daily_velocity"])

        # REASON — enough days of cover? (never-sold items have cover == inf,
        # so `inf >= reorder_point` is True and they skip for free.)
        if cover >= reorder_point:
            continue

        # PLAN — how many to order so we survive lead time + safety buffer.
        qty = suggest_reorder_qty(
            c["daily_velocity"], DEFAULT_LEAD_TIME_DAYS, DEFAULT_SAFETY_DAYS
        )

        # SELF-CORRECT — reject an absurd number instead of proposing it.
        if not is_qty_sane(qty):
            errors.append(f"decide_reorders: insane qty {qty} for {c['name']!r}")
            continue

        # PROPOSE — a sticky note for the owner to approve. We NEVER auto-buy.
        proposals.append({**c, "days_of_cover": cover, "reorder_qty": qty})

    return {"proposals": proposals, "errors": errors}


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
            {"medicine_id": 3, "name": "Rare Syrup", "current_stock": 1, "daily_velocity": 0.0},      # never sells -> skip (inf)
        ]
    }

    print("========== decide_reorders ==========")
    out = decide_reorders(test_state)
    print("proposals:")
    print(json.dumps(out.get("proposals", []), indent=2, ensure_ascii=False))
    print("errors:", out.get("errors", []))
    # Expected once you implement it: ONE proposal (Crocin), the other two skipped.
