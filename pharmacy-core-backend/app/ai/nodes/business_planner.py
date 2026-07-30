"""Planning node for the Business Intelligence Agent."""

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from app.ai.llm import get_llm
from app.ai.prompts.planner_prompt import (
    PLANNER_SYSTEM_PROMPT,
)
from app.ai.schemas.planner import PlannerOutput
from app.ai.state.business_state import BusinessState
from app.ai.utils.message_utils import (
    get_latest_user_message,
)


"""This is V2 planner node with production-grade architecture."""


def business_planner(
    state: BusinessState,
) -> BusinessState:
    """
    Analyze the user's latest message and decide
    which business capabilities are required.
    """

    structured_llm = get_llm().with_structured_output(
        PlannerOutput
    )

    # Read the latest user message from conversation history.
    latest_question = get_latest_user_message(state)

    messages = [
        SystemMessage(
            content=PLANNER_SYSTEM_PROMPT,
        ),
        HumanMessage(
            content=latest_question,
        ),
    ]

    result = structured_llm.invoke(messages)

    return {
        "plan": result.tasks,
        # Reset the per-turn reflection budget. reflection_count is checkpointed,
        # so without this a new question would inherit the previous turn's count
        # and could skip the reflection loop entirely.
        "reflection_count": 0,
    }