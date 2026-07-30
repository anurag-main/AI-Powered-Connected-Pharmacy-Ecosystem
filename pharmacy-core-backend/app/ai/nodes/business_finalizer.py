"""Terminal node — record the final analysis in conversation history.

Runs once, only when the reflection loop finishes, so exactly ONE assistant
message is appended per user turn. (The analyzer no longer writes messages; it
reruns on every reflection cycle and would otherwise add a draft each pass.)
"""
from langchain_core.messages import AIMessage

from app.ai.state.business_state import BusinessState


def business_finalizer(state: BusinessState) -> dict:
    """Append the final answer to the conversation as a single AI message."""
    return {"messages": [AIMessage(content=state["answer"])]}
