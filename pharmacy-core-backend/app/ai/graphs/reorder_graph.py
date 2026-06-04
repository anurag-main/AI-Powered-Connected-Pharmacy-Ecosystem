"""The compiled reorder LangGraph (the orchestration).

Wires the 2 reorder nodes into one runnable. A single
`get_reorder_graph().invoke({})` runs the whole nightly check end-to-end.

Wire order:
    START
      → fetch_candidates   (DB → every medicine's stock + velocity)
      → decide_reorders    (reason → plan → self-correct → proposals)
      → END

Why a graph for just 2 nodes (and not one plain function)?
    1. Same shape as the billing graph — one mental model for the whole project.
    2. The clipboard (state) + the errors reducer come for free.
    3. It leaves an obvious seam to add a 3rd node later: an LLM "judgment" node
       for the fuzzy cases (brand-new medicine with 0 velocity, batch expiring
       before it could sell). THAT is where the LLM earns its place — the math
       here is deterministic and needs none.

Singleton via lru_cache — compile once per process, same as get_billing_graph().
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.ai.nodes.decide_reorders import decide_reorders
from app.ai.nodes.fetch_candidates import fetch_candidates
from app.ai.state.reorder_state import ReorderState


@lru_cache(maxsize=1)
def get_reorder_graph():
    """Build and compile the reorder graph (cached for the life of the process)."""
    builder = StateGraph(ReorderState)

    builder.add_node("fetch_candidates", fetch_candidates)
    builder.add_node("decide_reorders", decide_reorders)

    builder.add_edge(START, "fetch_candidates")
    builder.add_edge("fetch_candidates", "decide_reorders")
    builder.add_edge("decide_reorders", END)

    return builder.compile()


# ============================================================================
# End-to-end smoke test — the WHOLE reorder agent in one shot (real MySQL).
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
        print("(no proposals — either stock is healthy, or decide_reorders isn't implemented yet)")
    for p in proposals:
        print(f"  • {p['name']}: stock={p['current_stock']} cover={p['days_of_cover']:.1f}d "
              f"-> ORDER {p['reorder_qty']}")
    print("\nerrors:", final_state.get("errors", []))
