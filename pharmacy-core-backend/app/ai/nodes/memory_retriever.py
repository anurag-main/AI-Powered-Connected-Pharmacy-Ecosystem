"""Node responsible for retrieving long-term memories."""

from langchain_core.runnables import RunnableConfig

from app.ai.memory.memory_repository import (
    MemoryRepository,
)
from app.ai.state.business_state import (
    BusinessState,
)
from app.ai.utils.message_utils import (
    get_latest_user_message,
)


repository = MemoryRepository()


def memory_retriever(
    state: BusinessState,
    config: RunnableConfig,
) -> BusinessState:
    """
    Retrieve the most relevant long-term memories
    for the user's latest question.
    """

    thread_id = config["configurable"]["thread_id"]

    latest_question = get_latest_user_message(
        state,
    )

    retrieved_memories = repository.search_memories(
        query=latest_question,
        thread_id=thread_id,
        k=5,
    )

    return {
        "retrieved_memories": retrieved_memories,
    }