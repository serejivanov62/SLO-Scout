"""
MiniLM embedding implementation per T068
sentence-transformers all-MiniLM-L6-v2, ONNX runtime, 384-dim output
"""
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer

from .embedding_service import EmbeddingService


class MiniLMEmbedder(EmbeddingService):
    """
    On-premise embedding service using MiniLM model

    Per research.md: MiniLM provides 80% quality of large models at 5x speed
    Model: all-MiniLM-L6-v2
    Dimensions: 384
    Runtime: ONNX (CPU inference)
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    DIMENSION = 384

    def __init__(self, device: str = "cpu"):
        """
        Initialize MiniLM embedder

        Args:
            device: 'cpu' or 'cuda' (default: cpu for on-prem)
        """
        self.device = device
        self.model = SentenceTransformer(self.MODEL_NAME, device=device)

        # Optimize for CPU inference
        if device == "cpu":
            self.model = self.model.half()  # FP16 for faster CPU inference

    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for single text

        Args:
            text: Capsule template

        Returns:
            384-dim numpy array
        """
        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True  # L2 normalization for cosine similarity
        )
        return embedding

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for batch (optimized)

        Args:
            texts: List of capsule templates

        Returns:
            List of 384-dim numpy arrays

        Per T072: Batch 100 capsules for efficiency
        """
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=100,  # Optimal batch size per research.md
            show_progress_bar=False
        )
        return [emb for emb in embeddings]

    def get_dimension(self) -> int:
        """Get embedding dimension"""
        return self.DIMENSION

    def get_model_name(self) -> str:
        """Get model identifier"""
        return self.MODEL_NAME
