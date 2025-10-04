"""
Embedding service factory per T070
Selects embedder based on config, defaults to MiniLM for on-prem
"""
import os
from typing import Optional

from .embedding_service import EmbeddingService
from .minilm_embedder import MiniLMEmbedder
from .openai_embedder import OpenAIEmbedder


class EmbeddingServiceFactory:
    """
    Factory for creating embedding service instances

    Per research.md:
    - Default: MiniLM (on-prem, data sovereignty)
    - Alternative: OpenAI (opt-in for quality)
    """

    @staticmethod
    def create_embedder(
        model_type: Optional[str] = None,
        **kwargs
    ) -> EmbeddingService:
        """
        Create embedding service instance

        Args:
            model_type: "minilm" or "openai" (defaults to env var EMBEDDING_MODEL)
            **kwargs: Additional parameters for embedder

        Returns:
            EmbeddingService instance

        Environment Variables:
            EMBEDDING_MODEL: "minilm" (default) or "openai"
            OPENAI_API_KEY: Required if model_type="openai"
        """
        # Determine model type
        if model_type is None:
            model_type = os.getenv("EMBEDDING_MODEL", "minilm").lower()

        # Create embedder
        if model_type == "openai":
            api_key = kwargs.get("api_key") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY required for OpenAI embedder")

            return OpenAIEmbedder(api_key=api_key)

        elif model_type == "minilm":
            device = kwargs.get("device", "cpu")
            return MiniLMEmbedder(device=device)

        else:
            raise ValueError(f"Unknown model type: {model_type}. Use 'minilm' or 'openai'")

    @staticmethod
    def get_default() -> EmbeddingService:
        """
        Get default embedder (MiniLM for on-prem)

        Returns:
            MiniLMEmbedder instance
        """
        return MiniLMEmbedder()
