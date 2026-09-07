"""Storage and retrieval of long-term memories, scoped to one conversation.

MEMORY SCOPE
------------
Every memory is written and read under a :class:`MemoryScope`. Today a scope is one
conversation — a memory learned in thread A is invisible from thread B, which is what
keeps one pharmacist's conversation out of another's.

The scope is a small object rather than a bare ``thread_id`` string on purpose. It has
one field now and will gain ``business_id`` when authentication supplies a real
identity; :meth:`MemoryScope.as_filter` is then the only place that changes, instead of
every call site. Until then there is no identity above the conversation, so genuine
cross-conversation recall is not possible — that is a property of the missing auth
layer, not a bug in this file. Documented in ``docs/business_queries.md``.

The filter is applied on **both** write and read. Filtering only on read would put one
scope's data physically in another's result set and rely on a query parameter to hide
it; tagging on write means the isolation survives a mistake at the read end.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.documents import Document

from app.ai.memory.chroma_store import get_vector_store
from app.ai.memory.memory_policy import normalize_fact
from app.ai.schemas.memory import MemoryFact

DEFAULT_SEARCH_LIMIT = 5

# Bounds a scan for duplicate detection. A conversation accumulating more durable
# facts than this has a different problem than deduplication.
MAX_SCOPE_MEMORIES = 200


@dataclass(frozen=True)
class MemoryScope:
    """Who a memory belongs to.

    One field today. When auth lands, ``business_id`` joins it and ``as_filter``
    becomes an ``$and`` over both — no call site changes.
    """

    thread_id: str

    def __post_init__(self) -> None:
        if not self.thread_id or not self.thread_id.strip():
            raise ValueError(
                "MemoryScope requires a non-empty thread_id; an unscoped write would "
                "be readable from every conversation."
            )

    def as_filter(self) -> dict:
        """The Chroma metadata filter selecting exactly this scope."""

        return {"thread_id": self.thread_id}

    def as_metadata(self) -> dict:
        """The scope fields stamped onto a stored document."""

        return {"thread_id": self.thread_id}


class MemoryRepository:
    """Stores and retrieves long-term memories in ChromaDB."""

    def __init__(self) -> None:
        self.vector_store = get_vector_store()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_memory(self, memory: MemoryFact, scope: MemoryScope) -> None:
        """Store one memory under a scope.

        The policy gate runs in the persistor node, not here: this method's job is
        storage, and a repository that silently refuses writes is hard to reason about.
        """

        document = Document(
            page_content=memory.fact,
            metadata={
                **scope.as_metadata(),
                "category": memory.category,
                "confidence": memory.confidence,
                # Stored so duplicate detection is an exact metadata match rather
                # than a re-normalisation of every retrieved document.
                "normalized": normalize_fact(memory.fact),
            },
        )

        self.vector_store.add_documents([document])

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search_memories(
        self, query: str, scope: MemoryScope, k: int = DEFAULT_SEARCH_LIMIT
    ) -> list[Document]:
        """The most relevant memories in this scope for the current question."""

        return self.vector_store.similarity_search(
            query=query,
            k=k,
            filter=scope.as_filter(),
        )

    def existing_normalized_facts(self, scope: MemoryScope) -> set[str]:
        """Normalized forms of everything already stored in this scope.

        Feeds duplicate detection. Uses a metadata ``get`` rather than a similarity
        search: duplicates are an exact-match question, and embedding a query to
        answer it would cost an API call to do a worse job.
        """

        try:
            stored = self.vector_store.get(
                where=scope.as_filter(), limit=MAX_SCOPE_MEMORIES
            )
        except Exception:  # noqa: BLE001
            # Deduplication is an optimisation. If the store cannot answer, storing a
            # duplicate is a far better outcome than failing the user's request.
            return set()

        return {
            metadata.get("normalized", "")
            for metadata in (stored.get("metadatas") or [])
            if metadata
        }
