"""Agent node for the LangGraph Tool Calling workflow."""

from langchain_core.messages import SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.business_prompt import BUSINESS_SYSTEM_PROMPT
from app.ai.state.business_state import BusinessState
from app.ai.tools.business_tools import (
    get_expiry_summary,
    get_margin_summary,
    get_purchase_summary,
    get_return_summary,
    get_sales_summary,
)


def tool_agent(
    state: BusinessState,
) -> BusinessState:
    """
    AI Agent responsible for deciding whether
    business tools should be executed.

    The agent does NOT execute tools.

    It only reasons and requests tool calls.
    """

    llm = get_llm().bind_tools(
        [
            get_sales_summary,
            get_purchase_summary,
            get_return_summary,
            get_expiry_summary,
            get_margin_summary,
        ]
    )

    messages = [
        SystemMessage(
            content=BUSINESS_SYSTEM_PROMPT,
        ),
        *state["messages"],
    ]

    response = llm.invoke(messages)

    return {
        "messages": [response],
    }