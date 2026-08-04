"""LLM node for extracting long-term memories from conversations."""

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from app.ai.llm import get_llm
from app.ai.prompts.memory_prompt import (
    MEMORY_SYSTEM_PROMPT,
)
from app.ai.schemas.memory import (
    MemoryExtraction,
)
from app.ai.state.business_state import BusinessState


def memory_extractor(
    state: BusinessState,
) -> BusinessState:
    """
    Extract durable memories from the current conversation.

    This node analyzes the conversation history and identifies
    information that should be stored as long-term memory.
    """

    structured_llm = get_llm().with_structured_output(
        MemoryExtraction,
    )

    messages = [
        SystemMessage(
            content=MEMORY_SYSTEM_PROMPT,
        )
    ]

    # Provide the complete conversation.
    messages.extend(state["messages"])

    result = structured_llm.invoke(messages)

    return {
        "memories": result.memories,
    }