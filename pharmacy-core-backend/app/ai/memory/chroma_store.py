"""ChromaDB vector store used for long-term memory."""

from functools import lru_cache

from langchain_chroma import Chroma

from app.ai.memory.embedding_service import (
    get_embedding_model,
)


# Directory where Chroma persists data.
PERSIST_DIRECTORY = "memory_db"

# Collection used for long-term memories.
COLLECTION_NAME = "long_term_memory"


@lru_cache(maxsize=1)
def get_vector_store() -> Chroma:
    """
    Return the project-wide ChromaDB vector store.

    The vector store is initialized only once during the
    application's lifetime and reused everywhere.
    """

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embedding_model(),
        persist_directory=PERSIST_DIRECTORY,
    )