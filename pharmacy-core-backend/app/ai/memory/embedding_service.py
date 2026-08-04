"""Embedding service for long-term memory."""

from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from app.ai.config import OPENAI_API_KEY


@lru_cache(maxsize=1)
def get_embedding_model() -> OpenAIEmbeddings:
    """
    Return the project-wide embedding model.

    The model instance is cached so that it is created
    only once during the application's lifetime.
    """

    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=OPENAI_API_KEY,
    )


class EmbeddingService:
    """
    Service responsible for generating embeddings.
    """

    def create_embedding(
        self,
        text: str,
    ) -> list[float]:
        """
        Convert text into an embedding vector.
        """

        embedding_model = get_embedding_model()

        return embedding_model.embed_query(
            text,
        )