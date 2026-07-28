"""Reflection node for the Business Intelligence Agent."""

from app.ai.state.business_state import BusinessState


MINIMUM_CONFIDENCE = 0.80


def business_reflector(state: BusinessState) -> BusinessState:
    """
    Validate the LLM response before finishing the graph.
    """

    confidence = state["confidence"]

    if confidence < MINIMUM_CONFIDENCE:
        state["retry"] = True
        state["reflection"] = (
            "Confidence is too low. More business data is required."
        )
    else:
        state["retry"] = False
        state["reflection"] = (
            "Business analysis looks reliable."
        )

    return state