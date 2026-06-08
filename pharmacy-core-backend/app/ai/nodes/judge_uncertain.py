"""LangGraph node — judge_uncertain (the senior pharmacist's opinion = the LLM).

This is the ONE place an LLM is used in the reorder agent. decide_reorders set
aside the medicines with 0 recent sales (state['uncertain']) because no formula
can tell a brand-new product from dead stock. This node hands those — WITH
context (how new, the name) — to the LLM, which returns a structured judgment.

The LLM only SUGGESTS. is_qty_sane still guards the number, and every suggestion
is tagged needs_review=True so the OWNER approves it. Crisp math stayed in code;
only the fuzzy judgment came here.

Writes:
    state['proposals'] — LLM-suggested reorders (tagged source='llm', needs_review)
    state['errors']    — items the LLM mishandled / if the LLM was unavailable

Analogy (kid-level):
    The night manager couldn't decide on the no-sales items, so he asks the
    senior pharmacist who knows context: "this Vicks is new and it's winter —
    stock it" vs "this tonic is a year old and dead — drop it."
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.reorder_prompts import JUDGE_REORDER_SYSTEM_PROMPT_V1
from app.ai.schemas.reorder_judgment import ReorderJudgment
from app.ai.state.reorder_state import ReorderState
from app.ai.tools.reorder_tools import is_qty_sane


def judge_uncertain(state: ReorderState) -> dict:
    """Ask the LLM to judge the 0-sales items; turn 'reorder' verdicts into proposals."""

    uncertain = state.get("uncertain")
    if not uncertain:
        return {}  # nothing fuzzy to judge — no LLM call, no cost

    # Build ONE human message describing all uncertain items + their context.
    # (One call for the whole batch — never one API call per medicine.)
    lines = ["Medicines with 0 recent sales — judge each:"]
    for u in uncertain:
        lines.append(
            f'- medicine_id={u["medicine_id"]} name="{u["name"]}" '
            f'stock={u["current_stock"]} days_since_added={u.get("days_since_added", "?")}'
        )
    human = "\n".join(lines)

    # ===== THIS is the LLM. Two lines. Everything else is plumbing. =====
    try:
        structured = get_llm().with_structured_output(ReorderJudgment)
        result = structured.invoke([
            SystemMessage(content=JUDGE_REORDER_SYSTEM_PROMPT_V1),
            HumanMessage(content=human),
        ])
    except Exception:  # noqa: BLE001 — LLM down: degrade, don't crash the agent
        return {"errors": [f"judge_uncertain: LLM unavailable; {len(uncertain)} items need manual review"]}

    by_id = {u["medicine_id"]: u for u in uncertain}
    proposals: list[dict] = []
    errors: list[str] = []

    for j in (result.judgments or []):
        candidate = by_id.get(j.medicine_id)
        if candidate is None:
            continue                       # LLM returned an id we didn't ask about
        if j.action != "reorder":
            continue                       # 'watch' / 'ignore' -> not a reorder

        qty = j.suggested_qty or 0
        if not is_qty_sane(qty):           # self-correct even on the LLM's number
            errors.append(f"judge_uncertain: insane qty {qty} for {candidate['name']!r}")
            continue

        proposals.append({
            **candidate,
            "reorder_qty": qty,
            "source": "llm",               # so the UI marks it as an AI suggestion
            "needs_review": True,          # owner must approve
            "reason": j.reason,
            "confidence": j.confidence,
        })

    return {"proposals": proposals, "errors": errors}


# ============================================================================
# Smoke test — REAL LLM call (uses your active provider from .env).
#     python -m app.ai.nodes.judge_uncertain
# ============================================================================

if __name__ == "__main__":
    import json

    test_state: ReorderState = {
        "uncertain": [
            {"medicine_id": 7, "name": "Vicks Cough Syrup", "current_stock": 2, "days_since_added": 3},
            {"medicine_id": 9, "name": "Old Vitamin Tonic", "current_stock": 40, "days_since_added": 400},
        ]
    }

    print("========== judge_uncertain (real LLM) ==========")
    out = judge_uncertain(test_state)
    print(json.dumps(out, indent=2, ensure_ascii=False))
