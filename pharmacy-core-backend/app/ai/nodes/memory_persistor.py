"""Node responsible for persisting extracted memories."""

from langchain_core.runnables import RunnableConfig

from app.ai.memory.memory_repository import (
    MemoryRepository,
)
from app.ai.state.business_state import (
    BusinessState,
)


# Built on first use, not at import time — see the same note in memory_retriever.py.
_repository: MemoryRepository | None = None


def get_repository() -> MemoryRepository:
    """Return the shared MemoryRepository, creating it on first use."""

    global _repository

    if _repository is None:
        _repository = MemoryRepository()

    return _repository


def memory_persistor(
    state: BusinessState,
    config: RunnableConfig,
) -> BusinessState:
    """
    Persist extracted memories into ChromaDB.
    """

    thread_id = config["configurable"]["thread_id"]

    memories = state.get(
        "memories",
        [],
    )

    for memory in memories:
        get_repository().save_memory(
            memory=memory,
            thread_id=thread_id,
        )

    return {}