"""Business Intelligence Agent graph."""

from langgraph.graph import END, START, StateGraph

from app.ai.nodes.business_analyzer import business_analyzer
from app.ai.nodes.business_fetcher import business_fetcher
from app.ai.nodes.business_planner import business_planner
from app.ai.nodes.business_reflector import business_reflector
from app.ai.state.business_state import BusinessState


def should_retry(state: BusinessState) -> str:
    """
    Decide whether another analysis attempt is required.
    """

    if state["retry"]:
        return "retry"

    return "finish"


def get_business_graph():
    """
    Build and compile the Business Intelligence Agent graph.
    """

    graph = StateGraph(BusinessState)

    graph.add_node("planner", business_planner)
    graph.add_node("fetcher", business_fetcher)
    graph.add_node("analyzer", business_analyzer)
    graph.add_node("reflector", business_reflector)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "fetcher")
    graph.add_edge("fetcher", "analyzer")
    graph.add_edge("analyzer", "reflector")

    graph.add_conditional_edges(
        "reflector",
        should_retry,
        {
            "retry": "fetcher",
            "finish": END,
        },
    )

    return graph.compile()