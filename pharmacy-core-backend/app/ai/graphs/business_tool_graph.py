"""Native LangGraph Tool Calling graph."""

from langgraph.graph import (
    END,
    START,
    StateGraph,
)
from langgraph.prebuilt import ToolNode

from app.ai.nodes.tool_agent import tool_agent
from app.ai.state.business_state import BusinessState
from app.ai.tools.business_tools import (
    get_expiry_summary,
    get_margin_summary,
    get_purchase_summary,
    get_return_summary,
    get_sales_summary,
)

tools = [
    get_sales_summary,
    get_purchase_summary,
    get_return_summary,
    get_expiry_summary,
    get_margin_summary,
]

graph = StateGraph(BusinessState)

graph.add_node(
    "agent",
    tool_agent,
)

graph.add_node(
    "tools",
    ToolNode(tools),
)

graph.add_edge(
    START,
    "agent",
)