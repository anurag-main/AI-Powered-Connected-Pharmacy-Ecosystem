"""Native LangGraph Tool Calling graph."""

from langgraph.graph import (
    START,
    StateGraph,
)
from langgraph.prebuilt import (
    ToolNode,
    tools_condition,
)

from app.ai.nodes.tool_agent import tool_agent
from app.ai.state.business_state import BusinessState
from app.ai.tools.business_tools import (
    get_expiry_summary,
    get_margin_summary,
    get_purchase_summary,
    get_return_summary,
    get_sales_summary,
)


def get_business_tool_graph():
    """
    Build and compile the native LangGraph Tool Calling graph.
    """

    tools = [
        get_sales_summary,
        get_purchase_summary,
        get_return_summary,
        get_expiry_summary,
        get_margin_summary,
    ]

    graph = StateGraph(BusinessState)

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    graph.add_node(
        "agent",
        tool_agent,
    )

    graph.add_node(
        "tools",
        ToolNode(tools),
    )

    # ------------------------------------------------------------------
    # Flow
    # ------------------------------------------------------------------

    graph.add_edge(
        START,
        "agent",
    )

    graph.add_conditional_edges(
        "agent",
        tools_condition,
    )

    graph.add_edge(
        "tools",
        "agent",
    )

    return graph.compile()