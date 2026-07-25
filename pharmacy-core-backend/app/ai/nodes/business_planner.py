"""Planning node for the Business Intelligence Agent."""

from app.ai.state.business_state import BusinessState


def business_planner(state: BusinessState) -> BusinessState:
    """
    Decide what business metrics are required
    before answering the user's question.
    """

    question = state["question"].lower()

    if "profit" in question:
        plan = [
            "sales",
            "purchases",
            "returns",
            "expiry",
            "margin",
        ]

    elif "sales" in question:
        plan = [
            "sales",
        ]

    else:
        plan = [
            "sales",
            "purchases",
            "returns",
            "expiry",
            "margin",
        ]

    state["plan"] = plan

    return state