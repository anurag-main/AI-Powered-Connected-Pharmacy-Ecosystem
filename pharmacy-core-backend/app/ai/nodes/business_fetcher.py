"""Fetch the business data the planner asked for."""

from app.ai.state.business_state import BusinessState
from app.ai.tools.business_tools import get_business_metrics


def business_fetcher(state: BusinessState) -> dict:
    """Execute every planned query and collect the results.

    The plan is a list of validated BusinessQuery objects, so there is nothing left
    to interpret here — this node only runs them and hands back what came out.
    """

    return {
        "business_metrics": get_business_metrics(state["plan"]),
    }
