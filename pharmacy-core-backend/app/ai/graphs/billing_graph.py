"""The compiled billing LangGraph.

Wires the 5 billing nodes into a single runnable graph. ONE call to
`get_billing_graph().invoke({...})` runs the whole pipeline end-to-end.

Analogy (kid-level):
    The 5 helpers know their jobs but don't know the ORDER. The manager
    (this graph) holds the instruction card:
        START -> Rohit -> Priya -> Sanjay -> Meera -> Mom -> END
    He doesn't do any of the work himself — he just calls each helper
    in turn and carries the notebook (state) between them.

Wire order:
    START
      → extract_intent      (free text → ExtractedIntent)
      → resolve_medicine    (names → DB medicine_ids)
      → select_batch        (medicine_ids → FEFO batches)
      → compute_pricing     (batched_items → unit_price + line_total + total)
      → persist_sale        (atomic 4-table transaction)
      → END

Linear graph (no conditional routing) — each node guards its own input,
so a failure upstream propagates as soft errors through state['errors']
and downstream nodes degrade gracefully (their own guards fire).

A future enhancement is conditional edges that short-circuit to END on
errors — but it's NOT needed yet because every node already no-ops cleanly
on bad/missing input. Adding it now would be premature optimization.

Singleton via lru_cache:
    The compiled graph is reused across requests. Compiling it once costs
    a few ms, but doing so per HTTP request would waste latency. Same
    pattern as get_llm().
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.ai.nodes.compute_pricing import compute_pricing
from app.ai.nodes.extract_intent import extract_intent
from app.ai.nodes.persist_sale import persist_sale
from app.ai.nodes.resolve_medicine import resolve_medicine
from app.ai.nodes.select_batch import select_batch
from app.ai.state.billing_state import BillingState


@lru_cache(maxsize=1)
def get_billing_graph():
    """Build and compile the billing graph (cached for the life of the process)."""
    builder = StateGraph(BillingState)

    # ----- Register every node by name -----
    builder.add_node("extract_intent", extract_intent)
    builder.add_node("resolve_medicine", resolve_medicine)
    builder.add_node("select_batch", select_batch)
    builder.add_node("compute_pricing", compute_pricing)
    builder.add_node("persist_sale", persist_sale)

    # ----- Wire them in a straight line -----
    builder.add_edge(START, "extract_intent")
    builder.add_edge("extract_intent", "resolve_medicine")
    builder.add_edge("resolve_medicine", "select_batch")
    builder.add_edge("select_batch", "compute_pricing")
    builder.add_edge("compute_pricing", "persist_sale")
    builder.add_edge("persist_sale", END)

    return builder.compile()


@lru_cache(maxsize=1)
def get_quote_graph():
    """PREVIEW graph — same nodes as the sale graph but STOPS before persist.

    Wiring: START -> extract_intent -> resolve_medicine -> select_batch
            -> compute_pricing -> END

    Used by POST /quote. Produces priced line items + total WITHOUT writing any
    Sale/SaleItem rows or decrementing stock. The owner reviews/edits this preview,
    then 'Print Bill' calls the confirm graph to actually persist.

    Reuses the exact same node functions — only the wiring differs. This is the
    payoff of pure state-in/state-out nodes.
    """
    builder = StateGraph(BillingState)

    builder.add_node("extract_intent", extract_intent)
    builder.add_node("resolve_medicine", resolve_medicine)
    builder.add_node("select_batch", select_batch)
    builder.add_node("compute_pricing", compute_pricing)

    builder.add_edge(START, "extract_intent")
    builder.add_edge("extract_intent", "resolve_medicine")
    builder.add_edge("resolve_medicine", "select_batch")
    builder.add_edge("select_batch", "compute_pricing")
    builder.add_edge("compute_pricing", END)  # <-- no persist_sale

    return builder.compile()


@lru_cache(maxsize=1)
def get_confirm_graph():
    """FINALIZE graph — no LLM. Reprices owner-reviewed items, then persists.

    Wiring: START -> compute_pricing -> persist_sale -> END

    Used by POST /confirm. The caller supplies already-resolved line items
    (medicine_id, batch_id, quantity, ...) as `batched_items` in the initial
    state. compute_pricing RE-FETCHES the MRP from the DB (so the client can
    never tamper with the price), then persist_sale writes the atomic sale.

    No extract_intent / resolve_medicine here: the medicines were already
    identified during the quote step, so we skip the LLM and DB lookups and
    go straight to authoritative pricing + persistence.
    """
    builder = StateGraph(BillingState)

    builder.add_node("compute_pricing", compute_pricing)
    builder.add_node("persist_sale", persist_sale)

    builder.add_edge(START, "compute_pricing")
    builder.add_edge("compute_pricing", "persist_sale")
    builder.add_edge("persist_sale", END)

    return builder.compile()


# ============================================================================
# End-to-end smoke test — the WHOLE pipeline in one shot.
#
# Walks: pharmacist sentence -> LLM extraction -> DB lookups -> FEFO -> Decimal
# pricing -> atomic DB write -> returned sale_id. Touches real MySQL and the
# real NVIDIA endpoint.
#
# Run with:
#     cd c:\ai-pharmacy-ecosystem\pharmacy-core-backend
#     .\venv\Scripts\Activate.ps1
#     python -m app.ai.graphs.billing_graph
# ============================================================================

if __name__ == "__main__":
    import json

    from app.core.database import SessionLocal as _SessionLocal
    from app.repositories.sqlalchemy_batch_repository import (
        SQLAlchemyBatchRepository as _BatchRepo,
    )
    from app.repositories.sqlalchemy_medicine_repository import (
        SQLAlchemyMedicineRepository as _MedRepo,
    )

    # ---- Pre-flight: discover known-good data so the test adapts ----
    with _SessionLocal() as _db:
        _meds = _MedRepo(_db).list_all()
        _batch = _BatchRepo(_db).select_fefo(_meds[0].id) if _meds else None

    if not _meds:
        print("!! No medicines in DB.")
        raise SystemExit(1)
    if _batch is None:
        print("!! No usable batch (FEFO returned None). Run scripts.seed_test_batch first.")
        raise SystemExit(1)

    print(f"Pre-flight OK. Will sell from {_meds[0].name!r} batch {_batch.batch_number!r} (qty={_batch.quantity}).\n")

    # Compose a realistic pharmacist sentence using the known medicine name.
    sentence = (
        f"give me 1 strip {_meds[0].name} for Anurag 9876543210"
    )

    initial_state: BillingState = {"pharmacist_input": sentence}

    graph = get_billing_graph()

    print(f"========== Running the full graph ==========")
    print(f"INPUT: {sentence!r}\n")
    final_state = graph.invoke(initial_state)
    print("FINAL STATE:")
    # `expiry_date` in batched/priced items is already a string. Everything else
    # in state is JSON-safe by design.
    print(json.dumps(final_state, indent=2, ensure_ascii=False, default=str))

    if final_state.get("sale_id"):
        print(f"\nSUCCESS -- invoice id {final_state['sale_id']} written to MySQL.")
    else:
        print(f"\nFAILED -- no sale_id in final state. Check errors above.")
