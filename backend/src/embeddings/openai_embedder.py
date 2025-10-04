"""
OpenAI embedding implementation per T069
text-embedding-ada-002, 1536-dim output, opt-in config
"""
from typing import List
import numpy as np
import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from .embedding_service import EmbeddingService


class OpenAIEmbedder(EmbeddingService):
    """
    SaaS embedding service using OpenAI API

    Per research.md: OpenAI option for quality-over-cost tradeoff
    Model: text-embedding-ada-002
    Dimensions: 1536
    """

    MODEL_NAME = "text-embedding-ada-002"
    DIMENSION = 1536

    def __init__(self, api_key: str):
        """
        Initialize OpenAI embedder

        Args:
            api_key: OpenAI API key
        """
        self.api_key = api_key
        openai.api_key = api_key

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding via OpenAI API

        Args:
            text: Capsule template

        Returns:
            1536-dim numpy array

        Includes retry logic per T076 for rate limit handling
        """
        response = openai.Embedding.create(
            model=self.MODEL_NAME,
            input=text
        )

        embedding = response["data"][0]["embedding"]
        return np.array(embedding, dtype=np.float32)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for batch via OpenAI API

        Args:
            texts: List of capsule templates (max 2048 per request)

        Returns:
            List of 1536-dim numpy arrays
        """
        # OpenAI API supports batch requests
        response = openai.Embedding.create(
            model=self.MODEL_NAME,
            input=texts[:2048]  # API limit
        )

        embeddings = [
            np.array(item["embedding"], dtype=np.float32)
            for item in response["data"]
        ]
        return embeddings

    def get_dimension(self) -> int:
        """Get embedding dimension"""
        return self.DIMENSION

    def get_model_name(self) -> str:
        """Get model identifier"""
        return self.MODEL_NAME
