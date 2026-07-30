"""Business Intelligence Agent graph."""

from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.ai.nodes.business_analyzer import business_analyzer
from app.ai.nodes.business_fetcher import business_fetcher
from app.ai.nodes.business_finalizer import business_finalizer
from app.ai.nodes.business_planner import business_planner
from app.ai.nodes.business_reflector import business_reflector
from app.ai.state.business_state import BusinessState


MAX_REFLECTIONS = 2


def should_retry(state: BusinessState) -> str:
    """
    Decide whether another reflection cycle is required.

    The graph retries only when:
    1. The reflector requests additional business metrics.
    2. The maximum reflection limit has not been reached.
    """

    if (
        state["retry"]
        and state["reflection_count"] < MAX_REFLECTIONS
    ):
        return "retry"

    return "finish"


@lru_cache(maxsize=1)
def get_business_graph():
    """
    Build and compile the Business Intelligence Agent graph.

    Compiled once per process (lru_cache) so the MemorySaver — and therefore
    the conversation memory it holds — survives across requests. Building a
    fresh saver on every call would silently discard every checkpoint.
    """

    graph = StateGraph(BusinessState)

    # Nodes
    graph.add_node("planner", business_planner)
    graph.add_node("fetcher", business_fetcher)
    graph.add_node("analyzer", business_analyzer)
    graph.add_node("reflector", business_reflector)
    graph.add_node("finalizer", business_finalizer)

    # Initial flow
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "fetcher")
    graph.add_edge("fetcher", "analyzer")
    graph.add_edge("analyzer", "reflector")

    # Reflection loop -> finalizer records the answer once before ending.
    graph.add_conditional_edges(
        "reflector",
        should_retry,
        {
            "retry": "fetcher",
            "finish": "finalizer",
        },
    )
    graph.add_edge("finalizer", END)

    return graph.compile(checkpointer=MemorySaver())
