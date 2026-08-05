"""LLM node for analyzing pharmacy business metrics."""

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from app.ai.llm import get_llm
from app.ai.prompts.business_prompt import (
    BUSINESS_SYSTEM_PROMPT,
)
from app.ai.schemas.business_analysis import (
    BusinessAnalysis,
)
from app.ai.state.business_state import (
    BusinessState,
)
from app.ai.utils.message_utils import (
    get_latest_user_message,
)


def business_analyzer(
    state: BusinessState,
) -> BusinessState:
    """
    Analyze pharmacy business metrics while considering
    long-term user memories.
    """

    structured_llm = get_llm().with_structured_output(
        BusinessAnalysis
    )

    latest_question = get_latest_user_message(
        state,
    )

    retrieved_memories = "\n".join(
        memory.page_content
        for memory in state.get(
            "retrieved_memories",
            [],
        )
    )

    prompt = f"""
Business Question:
{latest_question}
"""

    if retrieved_memories:
        prompt += f"""

Retrieved Long-Term Memories:
{retrieved_memories}
"""

    prompt += f"""

Business Metrics:
{state["business_metrics"]}
"""

    messages = [
        SystemMessage(
            content=BUSINESS_SYSTEM_PROMPT,
        )
    ]

    # Complete conversation history
    messages.extend(
        state["messages"],
    )

    # Business context
    messages.append(
        HumanMessage(
            content=prompt,
        )
    )

    result = structured_llm.invoke(
        messages,
    )

    return {
        "answer": result.summary,
        "confidence": result.confidence,
    }