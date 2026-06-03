"""LangGraph node — resolve_medicine (voice-tolerant, confidence-gated).

Maps each spoken item name to a catalog Medicine id, tolerating speech-to-text
mangling ("crossing 200mg" -> "Crocin 500mg") WITHOUT auto-billing the wrong
medicine on garbage input.

Stages (cheap → smart):
  1. EXACT  — normalized name == catalog name → bill it, no LLM.
  2. FUZZY  — rapidfuzz shortlists ~5 candidate names (dose-stripped) + scores.
  3. CONFIRM— ONE LLM call picks the best candidate + a confidence per item.

Gating (the safety net the owner asked for):
  - Strong match (score ≥ 90, or LLM "high" with score ≥ 70) → auto-billed.
  - Weak match (LLM unsure / low score) → NOT auto-billed; flagged
    needs_confirm=True with candidate options for the owner to confirm/correct.
  - No candidate at all / LLM picks null → reported in errors (amber box).

Both auto-billed AND needs_confirm items flow through pricing (so the owner sees
a price either way); the frontend just shows needs_confirm ones in a separate
"confirm these" section instead of the main bill.
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

# Auto-bill thresholds. Above STRONG_SCORE we trust the fuzzy match outright;
# otherwise we need the LLM to say "high" AND a reasonable score.
_STRONG_SCORE = 90.0
_CONFIDENT_SCORE = 70.0


def _confirm_matches(pending: list[tuple[dict, list[str]]]) -> list[tuple[str | None, str]]:
    """One LLM call to pick the best catalog name + confidence for each item.

    `pending` is (item, candidate_names). Returns (chosen_name_or_None, confidence)
    in the same order. On LLM error, returns all (None, "low") so we degrade to
    "needs confirm / not found" rather than crash.
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
    except Exception:  # noqa: BLE001
        return [(None, "low")] * len(pending)

    decisions = result.matches or []
    out: list[tuple[str | None, str]] = []
    for i in range(len(pending)):
        if i < len(decisions):
            d = decisions[i]
            out.append((d.chosen, (d.confidence or "low").lower()))
        else:
            out.append((None, "low"))
    return out


def resolve_medicine(state: BillingState) -> dict:
    """Resolve each extracted item to a Medicine id, gating uncertain matches."""

    extracted = state.get("extracted_intent")
    if not extracted or not extracted.get("items"):
        return {"errors": ["resolve_medicine: no items to resolve"]}

    items = extracted["items"]
    resolved_items: list[dict] = []
    errors: list[str] = []

    with SessionLocal() as db:
        catalog = SQLAlchemyMedicineRepository(db).list_all()

    catalog_names = [m.name for m in catalog]
    norm_to_id = {normalize_medicine_name(m.name): m.id for m in catalog}
    name_to_id = {m.name: m.id for m in catalog}

    # Stage 1 (exact) + Stage 2 (fuzzy shortlist). `pending` holds the scored
    # shortlists so we can gate after the LLM confirm.
    pending: list[tuple[dict, list[tuple[str, float]]]] = []
    for item in items:
        norm = normalize_medicine_name(item["name"])
        if norm in norm_to_id:
            resolved_items.append({**item, "medicine_id": norm_to_id[norm], "match": "exact"})
            continue
        cands = shortlist(item["name"], catalog_names)  # [(name, score), ...]
        if not cands:
            errors.append(f"Medicine not found: {item['name']!r}")
            continue
        pending.append((item, cands))

    # Stage 3 — one LLM confirm for all fuzzy items, then gate by confidence+score.
    if pending:
        decisions = _confirm_matches([(it, [n for n, _ in cands]) for it, cands in pending])
        for (item, cands), (chosen, confidence) in zip(pending, decisions):
            if not chosen or chosen not in name_to_id:
                errors.append(f"Medicine not found: {item['name']!r}")
                continue

            chosen_score = next((s for n, s in cands if n == chosen), 0.0)
            strong = chosen_score >= _STRONG_SCORE
            confident = confidence == "high" and chosen_score >= _CONFIDENT_SCORE

            base = {
                **item,
                "name": chosen,
                "medicine_id": name_to_id[chosen],
                "matched_from": item["name"],
                "matched_to": chosen,
            }
            if strong or confident:
                base["match"] = "fuzzy"
                resolved_items.append(base)
            else:
                # Uncertain — don't auto-bill. Flag for owner confirmation and
                # carry the candidate options so the UI can offer a dropdown.
                base["match"] = "suggested"
                base["needs_confirm"] = True
                base["candidates"] = [
                    {"medicine_id": name_to_id[n], "name": n}
                    for n, _ in cands if n in name_to_id
                ]
                resolved_items.append(base)

    return {"resolved_items": resolved_items, "errors": errors}


# ============================================================================
# Smoke test — runs against your REAL local MySQL + the LLM.
#     python -m app.ai.nodes.resolve_medicine
# ============================================================================

if __name__ == "__main__":
    test_state: BillingState = {
        "extracted_intent": {
            "items": [
                {"name": "Paracetamol 500mg", "quantity": 1, "unit": "strip"},   # exact
                {"name": "crossing 200 mg", "quantity": 1, "unit": "strip"},      # fuzzy -> Crocin
                {"name": "mat CB", "quantity": 1, "unit": "strip"},               # fuzzy -> Mtac B
                {"name": "man address", "quantity": 1, "unit": "strip"},          # weak -> needs_confirm/not found
                {"name": "Unicorn Dust 999mg", "quantity": 1, "unit": "tube"},    # not found
            ],
            "customer_name": "Anurag",
            "customer_phone": "9876543210",
        }
    }

    print("========== resolve_medicine (confidence-gated) ==========")
    out = resolve_medicine(test_state)
    for it in out["resolved_items"]:
        tag = "CONFIRM?" if it.get("needs_confirm") else "billed  "
        extra = f" (heard '{it.get('matched_from')}')" if it.get("matched_from") else ""
        print(f"  [{tag}] {it['name']}{extra}  match={it.get('match')}")
    print("  errors:", out["errors"])
