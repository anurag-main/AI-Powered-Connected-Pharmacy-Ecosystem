"""Business Intelligence Agent graph."""

from langgraph.graph import END, START, StateGraph

from app.ai.nodes.business_analyzer import business_analyzer
from app.ai.nodes.business_fetcher import business_fetcher
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


def get_business_graph():
    """
    Build and compile the Business Intelligence Agent graph.
    """

    graph = StateGraph(BusinessState)

    # Nodes
    graph.add_node("planner", business_planner)
    graph.add_node("fetcher", business_fetcher)
    graph.add_node("analyzer", business_analyzer)
    graph.add_node("reflector", business_reflector)

    # Initial flow
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "fetcher")
    graph.add_edge("fetcher", "analyzer")
    graph.add_edge("analyzer", "reflector")

    # Reflection loop
    graph.add_conditional_edges(
        "reflector",
        should_retry,
        {
            "retry": "fetcher",
            "finish": END,
        },
    )

    return graph.compile()