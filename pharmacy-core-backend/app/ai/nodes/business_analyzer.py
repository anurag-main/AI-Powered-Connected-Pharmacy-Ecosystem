"""LLM node for analyzing pharmacy business metrics."""

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.business_prompt import BUSINESS_SYSTEM_PROMPT
from app.ai.schemas.business_analysis import BusinessAnalysis
from app.ai.state.business_state import BusinessState


def business_analyzer(state: BusinessState) -> BusinessState:
    """
    Analyze the collected business metrics using the LLM.
    """

    structured_llm = get_llm().with_structured_output(
        BusinessAnalysis
    )

    messages = [
        SystemMessage(
            content=BUSINESS_SYSTEM_PROMPT,
        ),
        HumanMessage(
            content=f"""
Business Question:
{state["question"]}

Business Metrics:
{state["business_metrics"]}
"""
        ),
    ]

    result = structured_llm.invoke(messages)

    state["answer"] = result.summary
    state["confidence"] = result.confidence

    return state