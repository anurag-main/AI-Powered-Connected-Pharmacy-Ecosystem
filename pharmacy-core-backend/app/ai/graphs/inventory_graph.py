"""Inventory Risk Agent graph.

    START -> planner -> fetcher -> analyzer -> END
            (planner skipped when the caller already supplied a query)

Three nodes, linear, no loop. The same shape as the expiry agent, for the same
reasons: LangGraph earns its place for the checkpointed conversation state and for
putting this agent on the same footing as the others for a Supervisor to route to
later - not for branching it does not need.

There is deliberately **no reflection loop**. The query is a single object with
defaults and the calculation is deterministic: a second pass over the same target
cover returns byte-identical numbers. A retry could only burn a model call.
"""

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.ai.nodes.inventory_analyzer import inventory_analyzer
from app.ai.nodes.inventory_fetcher import inventory_fetcher
from app.ai.nodes.inventory_planner import inventory_planner
from app.ai.observability import observe_node
from app.ai.state.inventory_state import InventoryState

# Identifies this agent in every log line it produces.
AGENT_NAME = "inventory"

# A property of the deployed graph, not of any one run.
AGENT_VERSION = "inventory-agent-v1"


def _entry_point(state: InventoryState) -> str:
    """Plan only when there is nothing to plan from.

    The chat endpoint sends a question and needs the planner. The dashboard already
    HAS the target cover, the risk level and the sort - they came from dropdowns.
    Making it phrase a sentence for the planner to parse back into the same values
    would cost a model call and, worse, let the planner pick a different target from
    the one on screen.
    """

    return "fetcher" if state.get("query") is not None else "planner"


@lru_cache(maxsize=1)
def get_inventory_graph():
    """Build and compile the Inventory Risk Agent graph.

    Cached so the ``MemorySaver`` survives across requests - without it every call
    would start a fresh checkpointer and the conversation would reset each turn.
    """

    graph = StateGraph(InventoryState)

    graph.add_node(
        "planner", observe_node("planner", agent=AGENT_NAME)(inventory_planner)
    )
    graph.add_node(
        "fetcher", observe_node("fetcher", agent=AGENT_NAME)(inventory_fetcher)
    )
    graph.add_node(
        "analyzer", observe_node("analyzer", agent=AGENT_NAME)(inventory_analyzer)
    )

    graph.add_conditional_edges(
        START, _entry_point, {"planner": "planner", "fetcher": "fetcher"}
    )
    graph.add_edge("planner", "fetcher")
    graph.add_edge("fetcher", "analyzer")
    graph.add_edge("analyzer", END)

    return graph.compile(checkpointer=MemorySaver())
