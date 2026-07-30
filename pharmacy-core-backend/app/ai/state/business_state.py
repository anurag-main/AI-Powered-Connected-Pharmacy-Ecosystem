"""Shared state for the Business Intelligence Agent."""

from langgraph.graph import MessagesState


class BusinessState(MessagesState):
    """
    Shared state passed between all Business Intelligence nodes.

    MessagesState provides:
    - messages: list[AnyMessage]
    - automatic message merging (add_messages reducer)

    We extend it with our business-specific workflow state.
    """

    # ----------------------------
    # Planner
    # ----------------------------
    plan: list[str]

    # ----------------------------
    # Data collected from tools
    # ----------------------------
    business_metrics: dict

    # ----------------------------
    # AI Analysis
    # ----------------------------
    answer: str
    confidence: float

    # ----------------------------
    # Reflection
    # ----------------------------
    reflection: str
    reflection_count: int
    retry: bool

    # ----------------------------
    # Errors
    # ----------------------------
    errors: list[str]

    # ----------------------------
    # Future (Observability)
    # ----------------------------
    execution_time_ms: int
    agent_version: str