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

Collected Business Metrics:
{state["business_metrics"]}

Business Analysis:
{state["answer"]}
"""
        ),
    ]

    result = structured_llm.invoke(messages)
    state["reflection_count"] = state.get("reflection_count", 0) + 1

    # Store reflection result
    state["retry"] = not result.sufficient
    state["reflection"] = result.reason

    # Merge newly requested tasks while preserving order. Ignore any capability
    # the LLM invented that we have no tool for, so an unknown task can't crash
    # the next fetch.
    for task in result.missing_tasks:
        if task in TOOL_REGISTRY and task not in state["plan"]:
            state["plan"].append(task)

    return state