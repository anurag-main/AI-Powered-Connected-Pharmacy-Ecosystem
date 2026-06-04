"""LangGraph node — fetch_candidates (the stock clerk).

The FIRST node of the reorder agent. It pulls every medicine's raw numbers
(current stock + recent sell-through speed) from the database and drops them
on the clipboard for the decision node to reason over.

Writes:
    state['candidates'] — [{medicine_id, name, current_stock, daily_velocity}, ...]

Analogy (kid-level):
    The stock clerk walks the aisles once, writes down for every medicine
    "how many on the shelf" and "how fast it's been selling", and hands the
    whole sheet to the night manager. He doesn't DECIDE anything — he just
    gathers the facts.

Why the node owns its own session (same as resolve_medicine):
    LangGraph nodes don't get FastAPI's Depends(get_db). So the node opens a
    short-lived SessionLocal, uses the repo, and the `with` block closes it —
    returning the connection to the pool. The SQL itself lives in the repo.
"""
from app.ai.state.reorder_state import ReorderState
from app.core.database import SessionLocal
from app.repositories.sqlalchemy_reorder_repository import SQLAlchemyReorderRepository


def fetch_candidates(state: ReorderState) -> dict:
    """Load every medicine's stock + velocity into state['candidates']."""
    with SessionLocal() as db:
        candidates = SQLAlchemyReorderRepository(db).get_reorder_candidates()
    return {"candidates": candidates}


# ============================================================================
# Smoke test — runs against your REAL local MySQL.
#     python -m app.ai.nodes.fetch_candidates
# ============================================================================

if __name__ == "__main__":
    import json

    out = fetch_candidates({})
    cands = out.get("candidates", [])
    print(f"========== fetch_candidates: {len(cands)} medicines ==========")
    print(json.dumps(cands, indent=2, ensure_ascii=False, default=str))
