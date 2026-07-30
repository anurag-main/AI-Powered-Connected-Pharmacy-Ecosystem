"""Reflection node for the Business Intelligence Agent."""

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.reflection_prompt import (
    REFLECTION_SYSTEM_PROMPT,
)
from app.ai.schemas.reflection import ReflectionOutput
from app.ai.state.business_state import BusinessState
from app.ai.tools.business_tools import TOOL_REGISTRY
from app.ai.utils.message_utils import get_latest_user_message


def business_reflector(state: BusinessState) -> dict:
    """
    Review the generated business analysis and determine
    whether additional business metrics are required.
    """

    structured_llm = get_llm().with_structured_output(
        ReflectionOutput
    )

    latest_question = get_latest_user_message(state)

    messages = [
        SystemMessage(
            content=REFLECTION_SYSTEM_PROMPT,
        ),
        HumanMessage(
            content=f"""
Business Question:
{latest_question}

Already collected capabilities:
{list((state.get("business_metrics") or {}).keys())}

Collected Business Metrics:
{state["business_metrics"]}

Business Analysis:
{state["answer"]}
"""
        ),
    ]

    result = structured_llm.invoke(messages)

    # Keep only capabilities that are REAL (in the registry) and NOT already
    # planned. Anything the LLM invented or already fetched is discarded.
    new_tasks = [
        task
        for task in result.missing_tasks
        if task in TOOL_REGISTRY and task not in state["plan"]
    ]

    # Return a partial update (no mutation, no re-emitting messages). Retry ONLY
    # when the reflector is unsatisfied AND there is genuinely new data to fetch;
    # re-fetching identical data changes nothing.
    return {
        "reflection_count": state.get("reflection_count", 0) + 1,
        "reflection": result.reason,
        "retry": (not result.sufficient) and bool(new_tasks),
        "plan": state["plan"] + new_tasks,
    }