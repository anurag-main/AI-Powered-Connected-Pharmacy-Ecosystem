"""Reflection node for the Business Intelligence Agent."""

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.reflection_prompt import (
    REFLECTION_SYSTEM_PROMPT,
)
from app.ai.schemas.reflection import ReflectionOutput
from app.ai.state.business_state import BusinessState
from app.ai.tools.business_tools import TOOL_REGISTRY


def business_reflector(state: BusinessState) -> BusinessState:
    """
    Review the generated business analysis and determine
    whether additional business metrics are required.
    """

    structured_llm = get_llm().with_structured_output(
        ReflectionOutput
    )

    messages = [
        SystemMessage(
            content=REFLECTION_SYSTEM_PROMPT,
        ),
        HumanMessage(
            content=f"""
Business Question:
{state["question"]}

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
    state["reflection_count"] = state.get("reflection_count", 0) + 1
    state["reflection"] = result.reason

    # Keep only capabilities that are REAL (in the registry) and NOT already
    # planned. Anything the LLM invented or already fetched is discarded.
    new_tasks = [
        task
        for task in result.missing_tasks
        if task in TOOL_REGISTRY and task not in state["plan"]
    ]

    # Retry ONLY when the reflector is unsatisfied AND there is genuinely new
    # data to fetch. Looping to re-fetch identical data changes nothing, so an
    # "insufficient" verdict with no new tasks finishes instead of spinning.
    state["retry"] = (not result.sufficient) and bool(new_tasks)
    state["plan"].extend(new_tasks)

    return state