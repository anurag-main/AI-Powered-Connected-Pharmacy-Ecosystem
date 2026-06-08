"""The compiled reorder LangGraph (the orchestration).

Wires the 3 reorder nodes into one runnable:
    START
      → fetch_candidates   (DB → every medicine's stock + velocity + age)
      → decide_reorders    (clear math cases → proposals; 0-sales → uncertain)
      → judge_uncertain    (LLM judges the fuzzy 0-sales items → more proposals)
      → END

Why an LLM only at the end (and the math in code)?
    decide_reorders answers everything that HAS a formula. judge_uncertain is the
    ONLY place an LLM is needed — the 0-sales judgment (new product vs dead stock)
    that no equation can make. crisp → code, fuzzy → LLM.

Both decide_reorders and judge_uncertain write state['proposals']; the reducer on
that field (see reorder_state.py) concatenates their lists.

Singleton via lru_cache — compile once per process, same as get_billing_graph().
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.ai.nodes.decide_reorders import decide_reorders
from app.ai.nodes.fetch_candidates import fetch_candidates
from app.ai.nodes.judge_uncertain import judge_uncertain
from app.ai.state.reorder_state import ReorderState


@lru_cache(maxsize=1)
def get_reorder_graph():
    """Build and compile the reorder graph (cached for the life of the process)."""
    builder = StateGraph(ReorderState)

    builder.add_node("fetch_candidates", fetch_candidates)
    builder.add_node("decide_reorders", decide_reorders)
    builder.add_node("judge_uncertain", judge_uncertain)

    builder.add_edge(START, "fetch_candidates")
    builder.add_edge("fetch_candidates", "decide_reorders")
    builder.add_edge("decide_reorders", "judge_uncertain")
    builder.add_edge("judge_uncertain", END)

    return builder.compile()


# ============================================================================
# End-to-end smoke test — the WHOLE reorder agent in one shot (real MySQL + LLM).
#     cd c:\ai-pharmacy-ecosystem\pharmacy-core-backend
#     .\venv\Scripts\Activate.ps1
#     python -m app.ai.graphs.reorder_graph
# ============================================================================

if __name__ == "__main__":
    import json

    final_state = get_reorder_graph().invoke({})

    print("========== Reorder agent — proposals ==========")
    proposals = final_state.get("proposals", [])
    if not proposals:
        print("(no proposals)")
    for p in proposals:
        src = p.get("source", "rule")
        cover = p.get("days_of_cover")
        cover_txt = f"{cover:.1f}d cover" if isinstance(cover, (int, float)) else "0 recent sales"
        reason = f"  — {p['reason']}" if p.get("reason") else ""
        print(f"  • [{src}] {p['name']}: stock={p['current_stock']}, {cover_txt} "
              f"-> ORDER {p['reorder_qty']}{reason}")
    print("\nerrors:", final_state.get("errors", []))
