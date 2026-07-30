"""Utilities for working with conversation messages."""

from langchain_core.messages import HumanMessage

from app.ai.state.business_state import BusinessState


def get_latest_user_message(
    state: BusinessState,
) -> str:
    """
    Return the latest HumanMessage from the conversation.

    Raises:
        ValueError: If no HumanMessage exists.
    """

    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content

    raise ValueError(
        "No HumanMessage found in conversation history."
    )