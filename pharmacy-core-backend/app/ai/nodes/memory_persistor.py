"""Node responsible for persisting extracted memories."""

from langchain_core.runnables import RunnableConfig

from app.ai.memory.memory_repository import (
    MemoryRepository,
)
from app.ai.state.business_state import (
    BusinessState,
)


repository = MemoryRepository()


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
        repository.save_memory(
            memory=memory,
            thread_id=thread_id,
        )

    return {}