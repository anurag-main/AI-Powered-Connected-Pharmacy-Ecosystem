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
from app.ai.tools.business_tools import BUSINESS_TOOLS


def get_business_tool_graph():
    """
    Build and compile the native LangGraph Tool Calling graph.
    """

    tools = BUSINESS_TOOLS

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