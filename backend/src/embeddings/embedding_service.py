"""
Embedding service interface per T067
"""
from abc import ABC, abstractmethod
from typing import List
import numpy as np


class EmbeddingService(ABC):
    """
    Abstract base class for embedding services

    Implementations:
    - MiniLMEmbedder: on-prem default (384-dim)
    - OpenAIEmbedder: SaaS opt-in (1536-dim)
    """

    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding vector for a single text

        Args:
            text: Input text (capsule template)

        Returns:
            Numpy array of embedding vector
        """
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts (batch processing)

        Args:
            texts: List of input texts

        Returns:
            List of numpy arrays (embeddings)
        """
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """
        Get embedding vector dimension

        Returns:
            Dimension size (384 for MiniLM, 1536 for OpenAI)
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """
        Get model identifier

        Returns:
            Model name string
        """
        pass
