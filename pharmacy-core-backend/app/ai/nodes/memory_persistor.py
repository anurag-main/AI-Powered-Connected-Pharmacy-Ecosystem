"""Node that persists extracted memories, subject to the write policy."""

import logging

from langchain_core.runnables import RunnableConfig

from app.ai.memory.memory_policy import filter_persistable, log_rejections
from app.ai.memory.memory_repository import MemoryRepository, MemoryScope
from app.ai.state.business_state import BusinessState

logger = logging.getLogger("app.ai.memory")

# Built on first use - see the same note in memory_retriever.py.
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
    """Persist the memories that pass the write policy.

    The extractor PROPOSES; this node DECIDES. Everything the model suggested is put
    through confidence, category and shape gates plus a duplicate check before any
    write - because a model authorising its own permanent writes is how a mislabelled
    figure and an off-topic remark ended up stored as durable fact in the QA pass.
    """

    memories = state.get("memories") or []

    if not memories:
        return {}

    scope = MemoryScope(thread_id=config["configurable"]["thread_id"])
    repository = get_repository()

    accepted, rejected = filter_persistable(
        memories,
        existing_normalized=repository.existing_normalized_facts(scope),
    )

    for memory in accepted:
        repository.save_memory(memory=memory, scope=scope)

    log_rejections(rejected)

    logger.info(
        "memory_persisted",
        extra={
            "proposed": len(memories),
            "stored": len(accepted),
            "rejected": len(rejected),
        },
    )

    return {}
