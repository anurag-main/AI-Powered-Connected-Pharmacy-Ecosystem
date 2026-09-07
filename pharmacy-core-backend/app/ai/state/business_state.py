"""Shared state for the Business Intelligence Agent.

Every field here is written by at least one node and read by at least one other.
That is the bar: state is the contract between nodes, and a field nobody writes is
worse than no field — it reads like a promise and silently supplies a default.

Removed in milestone 3 after a repository-wide search confirmed no writer:

  ``errors``             declared ``list[str]``, never appended to, and without a
                         reducer it would have overwritten rather than accumulated
                         had two nodes ever tried. Per-query failures already travel
                         inside ``business_metrics`` as ``{"error": ...}`` entries,
                         which is where the analyzer actually looks.
  ``execution_time_ms``  no node set it; the service measures the wall clock itself.
  ``agent_version``      no node set it; it is a property of the deployed graph, not
                         of one run, and now lives as ``AGENT_VERSION`` in
                         ``app.ai.graphs.business_graph``.

The API still returns ``execution_time_ms`` and ``agent_version`` — they moved from
dead state to real values computed where the information actually exists.
"""

from langchain_core.documents import Document
from langgraph.graph import MessagesState

from app.ai.schemas.business_query import BusinessQuery
from app.ai.schemas.memory import MemoryFact


class BusinessState(MessagesState):
    """State passed between all Business Intelligence nodes.

    ``MessagesState`` supplies ``messages`` plus the ``add_messages`` reducer.
    """

    # -- planner ---------------------------------------------------------
    # Validated queries, not capability names. The planner decides WHAT to ask;
    # the objects carry metric, dimension, period, sort and limit together so a
    # downstream node can never lose half the question.
    plan: list[BusinessQuery]

    # -- fetcher ---------------------------------------------------------
    # Keyed by BusinessQuery.key(), so "sales" and "sales by product last month"
    # coexist instead of one overwriting the other.
    business_metrics: dict

    # -- analyzer --------------------------------------------------------
    answer: str
    confidence: float

    # -- reflector -------------------------------------------------------
    reflection: str
    reflection_count: int
    retry: bool

    # -- memory ----------------------------------------------------------
    memories: list[MemoryFact]
    retrieved_memories: list[Document]
