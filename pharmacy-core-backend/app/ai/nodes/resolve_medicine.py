"""LangGraph node — resolve_medicine (now voice-tolerant).

Maps each spoken item name to a catalog Medicine id, tolerating the mis-hearings
that speech-to-text produces ("crossing 200mg" -> "Crocin 500mg").

Three-stage strategy (cheap → smart):
  1. EXACT  — normalized name equals a catalog name → resolve instantly (no cost).
  2. FUZZY  — otherwise, rapidfuzz narrows the catalog to ~5 candidate names.
  3. CONFIRM— ONE LLM call picks the best candidate per remaining item (it reasons
              phonetically + by pharmacy context; dosage mismatch is ignored).

Items the LLM can't match (chosen = null) are reported in state['errors'].
Resolved items carry match metadata (matched_from / matched_to / confidence) for
transparency and the upcoming owner-confirm UI.

Analogy (kid-level):
    The strict librarian (exact match) only finds books with the perfect title.
    For the rest, a helper pulls the few closest-looking titles off the shelf
    (fuzzy), and the smart pharmacist (LLM) says "that's the one you meant."
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.matching import shortlist
from app.ai.prompts.billing_prompts import MATCH_CONFIRM_SYSTEM_PROMPT_V1
from app.ai.schemas.match_result import MatchResult
from app.ai.state.billing_state import BillingState
from app.core.database import SessionLocal
from app.repositories.sqlalchemy_medicine_repository import SQLAlchemyMedicineRepository
from app.services.medicine_service import normalize_medicine_name


def _confirm_matches(pending: list[tuple[dict, list[str]]]) -> list[str | None]:
    """One LLM call to pick the best catalog name for each pending item.

    `pending` is a list of (item, candidate_names). Returns a list of chosen
    names (or None) in the SAME order. On any LLM error, returns all None so the
    caller degrades to "not found" rather than crashing.
    """
    lines = ["Spoken items and their candidates:"]
    for i, (item, candidates) in enumerate(pending, 1):
        lines.append(f'{i}. "{item["name"]}"  candidates: {candidates}')
    human = "\n".join(lines)

    try:
        structured = get_llm().with_structured_output(MatchResult)
        result = structured.invoke([
            SystemMessage(content=MATCH_CONFIRM_SYSTEM_PROMPT_V1),
            HumanMessage(content=human),
        ])
    except Exception:  # noqa: BLE001 — degrade gracefully on LLM/network failure
        return [None] * len(pending)

    decisions = result.matches or []
    # Map by position (the prompt requires same order, one per item). Bounds-checked.
    chosen: list[str | None] = []
    for i in range(len(pending)):
        chosen.append(decisions[i].chosen if i < len(decisions) else None)
    return chosen


def resolve_medicine(state: BillingState) -> dict:
    """Resolve each extracted item's (possibly mis-heard) name to a Medicine id."""

    extracted = state.get("extracted_intent")
    if not extracted or not extracted.get("items"):
        return {"errors": ["resolve_medicine: no items to resolve"]}

    items = extracted["items"]
    resolved_items: list[dict] = []
    errors: list[str] = []

    # Load the catalog once.
    with SessionLocal() as db:
        catalog = SQLAlchemyMedicineRepository(db).list_all()

    catalog_names = [m.name for m in catalog]
    norm_to_id = {normalize_medicine_name(m.name): m.id for m in catalog}
    name_to_id = {m.name: m.id for m in catalog}

    # ----- Stage 1 (exact) + Stage 2 (fuzzy shortlist) -----
    pending: list[tuple[dict, list[str]]] = []  # items needing LLM confirm
    for item in items:
        norm = normalize_medicine_name(item["name"])
        if norm in norm_to_id:
            resolved_items.append({**item, "medicine_id": norm_to_id[norm], "match": "exact"})
            continue

        candidates = shortlist(item["name"], catalog_names)
        if not candidates:
            errors.append(f"Medicine not found: {item['name']!r}")
            continue
        pending.append((item, candidates))

    # ----- Stage 3 (one LLM confirm call for all fuzzy items) -----
    if pending:
        chosen_names = _confirm_matches(pending)
        for (item, _candidates), chosen in zip(pending, chosen_names):
            if chosen and chosen in name_to_id:
                resolved_items.append({
                    **item,
                    "name": chosen,                 # show the REAL catalog name on the bill
                    "medicine_id": name_to_id[chosen],
                    "match": "fuzzy",
                    "matched_from": item["name"],   # keep the spoken text for transparency
                    "matched_to": chosen,
                })
            else:
                errors.append(f"Medicine not found: {item['name']!r}")

    return {"resolved_items": resolved_items, "errors": errors}


# ============================================================================
# Smoke test — runs against your REAL local MySQL + the LLM.
#     python -m app.ai.nodes.resolve_medicine
# ============================================================================

if __name__ == "__main__":
    import json

    test_state: BillingState = {
        "extracted_intent": {
            "items": [
                {"name": "Paracetamol 500mg", "quantity": 1, "unit": "strip"},   # exact
                {"name": "crossing 200 mg", "quantity": 1, "unit": "strip"},      # fuzzy -> Crocin
                {"name": "Unicorn Dust 999mg", "quantity": 1, "unit": "tube"},    # truly unknown
            ],
            "customer_name": "Anurag",
            "customer_phone": "9876543210",
        }
    }

    print("========== resolve_medicine (voice-tolerant) ==========")
    out = resolve_medicine(test_state)
    print(json.dumps(out, indent=2, ensure_ascii=False))
