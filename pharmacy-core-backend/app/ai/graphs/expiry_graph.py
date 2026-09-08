"""Expiry Risk Agent graph.

    START -> planner -> fetcher -> analyzer -> END

Three nodes, linear, no loop. LangGraph earns its place here for the checkpointed
conversation state and for putting the agent on the same footing as the BI agent for
the Supervisor to route to later — not for branching it does not need.

There is deliberately **no reflection loop**. The BI agent has one because its planner
picks from five metrics and can genuinely miss one. Here the query is a single object
with defaults, and the calculation is deterministic: a second pass over the same
window returns byte-identical numbers. A retry could only burn a model call.
"""

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.ai.nodes.expiry_analyzer import expiry_analyzer
from app.ai.nodes.expiry_fetcher import expiry_fetcher
from app.ai.nodes.expiry_planner import expiry_planner
from app.ai.observability import observe_node
from app.ai.state.expiry_state import ExpiryState

# Identifies this agent in every log line it produces.
AGENT_NAME = "expiry"

# A property of the deployed graph, not of any one run.
AGENT_VERSION = "expiry-agent-v1"


@lru_cache(maxsize=1)
def get_expiry_graph():
    """Build and compile the Expiry Risk Agent graph.

    Cached so the ``MemorySaver`` survives across requests — without it every call
    would start a fresh checkpointer and the conversation would reset each turn.
    """

    graph = StateGraph(ExpiryState)

    graph.add_node("planner", observe_node("planner", agent=AGENT_NAME)(expiry_planner))
    graph.add_node("fetcher", observe_node("fetcher", agent=AGENT_NAME)(expiry_fetcher))
    graph.add_node(
        "analyzer", observe_node("analyzer", agent=AGENT_NAME)(expiry_analyzer)
    )

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "fetcher")
    graph.add_edge("fetcher", "analyzer")
    graph.add_edge("analyzer", END)

    return graph.compile(checkpointer=MemorySaver())
