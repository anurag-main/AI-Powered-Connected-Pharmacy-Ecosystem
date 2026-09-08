"""Shared state for the Expiry Risk Agent.

Same bar as BusinessState: every field is written by one node and read by another.
No field exists "for later".
"""

from langgraph.graph import MessagesState

from app.ai.schemas.expiry_query import ExpiryRiskQuery, ExpiryRiskReport


class ExpiryState(MessagesState):
    """State passed between the expiry nodes.

    ``MessagesState`` supplies ``messages`` plus the ``add_messages`` reducer, so the
    agent gets conversation history on the same terms as the BI agent.
    """

    # -- planner ---------------------------------------------------------
    query: ExpiryRiskQuery

    # -- fetcher ---------------------------------------------------------
    # The full deterministic result. Held as the typed object rather than a dict so
    # the analyzer cannot quietly reshape it on the way through.
    report: ExpiryRiskReport

    # -- analyzer --------------------------------------------------------
    answer: str
    confidence: float
