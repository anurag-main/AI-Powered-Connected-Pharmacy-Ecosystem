"""Repository for managing long-term memories."""

from langchain_core.documents import Document

from app.ai.memory.chroma_store import (
    get_vector_store,
)
from app.ai.schemas.memory import (
    MemoryFact,
)


class MemoryRepository:
    """
    Repository responsible for storing and retrieving
    long-term memories.
    """

    def __init__(self) -> None:
        self.vector_store = get_vector_store()

    def save_memory(
        self,
        memory: MemoryFact,
    ) -> None:
        """
        Store a single memory in ChromaDB.
        """

        document = Document(
            page_content=memory.fact,
            metadata={
                "category": memory.category,
                "confidence": memory.confidence,
            },
        )

        self.vector_store.add_documents(
            [document],
        )

    def search_memories(
        self,
        query: str,
        k: int = 5,
    ) -> list[Document]:
        """
        Retrieve the most relevant memories.
        """

        return self.vector_store.similarity_search(
            query=query,
            k=k,
        )