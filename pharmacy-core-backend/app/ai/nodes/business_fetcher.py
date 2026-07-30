"""Fetch business data required by the planner."""

from app.ai.state.business_state import BusinessState
from app.ai.tools.business_tools import get_business_metrics


def business_fetcher(state: BusinessState) -> dict:
    """
    Execute the business plan by calling
    the required business tools.
    """

    return {
        "business_metrics": get_business_metrics(state["plan"]),
    }