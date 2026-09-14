"""Shared state for the Inventory Risk Agent.

Same bar as ExpiryState: every field is written by one node and read by another. No
field exists "for later".
"""

from langgraph.graph import MessagesState

from app.ai.schemas.inventory_query import InventoryRiskQuery, InventoryRiskReport


class InventoryState(MessagesState):
    """State passed between the inventory nodes.

    ``MessagesState`` supplies ``messages`` plus the ``add_messages`` reducer, so the
    agent gets conversation history on the same terms as the expiry and BI agents.
    """

    # -- planner ---------------------------------------------------------
    query: InventoryRiskQuery

    # -- fetcher ---------------------------------------------------------
    # The full deterministic result. Held as the typed object rather than a dict so
    # the analyzer cannot quietly reshape it on the way through.
    report: InventoryRiskReport

    # -- analyzer --------------------------------------------------------
    answer: str
    confidence: float
