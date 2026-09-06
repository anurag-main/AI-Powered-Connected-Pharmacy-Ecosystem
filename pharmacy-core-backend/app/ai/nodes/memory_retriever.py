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


# Built on first use, not at import time. Constructing MemoryRepository opens the
# ChromaDB client, so doing it at import meant merely importing this module (or any
# graph containing it) touched the on-disk vector store. Lazy construction keeps the
# runtime behaviour identical — same single shared instance — while letting callers
# that never run this node avoid the side effect entirely.
_repository: MemoryRepository | None = None


def get_repository() -> MemoryRepository:
    """Return the shared MemoryRepository, creating it on first use."""

    global _repository

    if _repository is None:
        _repository = MemoryRepository()

    return _repository


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

    retrieved_memories = get_repository().search_memories(
        query=latest_question,
        thread_id=thread_id,
        k=5,
    )

    return {
        "retrieved_memories": retrieved_memories,
    }