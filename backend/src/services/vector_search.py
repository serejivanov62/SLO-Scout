"""
Vector search service per T081
Queries Milvus for top-K similar capsules
Metadata filters by service/timestamp
Returns capsule IDs
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

from ..storage.vector_storage import VectorStorageClient


class VectorSearchService:
    """
    Service for semantic search over capsule embeddings

    Per research.md: Milvus HNSW index for sub-100ms queries
    """

    def __init__(self, vector_storage: VectorStorageClient):
        self.vector_storage = vector_storage

    def search_similar_capsules(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        service_name: Optional[str] = None,
        environment: Optional[str] = None,
        time_range_days: Optional[int] = None,
        min_similarity: float = 0.5
    ) -> List[Dict]:
        """
        Search for similar capsules using vector similarity

        Args:
            query_embedding: Query vector (384-dim for MiniLM, 1536-dim for OpenAI)
            top_k: Number of results to return
            service_name: Filter by service (optional)
            environment: Filter by environment (optional)
            time_range_days: Filter by time range in days (optional)
            min_similarity: Minimum similarity score (0-1)

        Returns:
            List of capsule matches with metadata:
            [
                {
                    "capsule_id": "uuid",
                    "fingerprint_hash": "hash",
                    "service_name": "payments-api",
                    "severity": "ERROR",
                    "time_bucket": 1699200000000,
                    "score": 0.95,
                    "distance": 0.05
                },
                ...
            ]
        """
        # Build time range filter
        time_range = None
        if time_range_days is not None:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=time_range_days)
            time_range = (
                int(start_time.timestamp() * 1000),
                int(end_time.timestamp() * 1000)
            )

        # Search Milvus
        results = self.vector_storage.search_similar(
            query_embedding=query_embedding,
            top_k=top_k,
            service_name=service_name,
            environment=environment,
            time_range=time_range
        )

        # Filter by minimum similarity
        filtered_results = [
            result for result in results
            if result['score'] >= min_similarity
        ]

        return filtered_results

    def search_by_template(
        self,
        template: str,
        embedding_service,
        top_k: int = 10,
        **kwargs
    ) -> List[Dict]:
        """
        Search for similar capsules by template text

        Args:
            template: Template text to search for
            embedding_service: EmbeddingService instance for generating query embedding
            top_k: Number of results
            **kwargs: Additional filters (service_name, environment, etc.)

        Returns:
            List of similar capsules
        """
        # Generate embedding for query template
        query_embedding = embedding_service.embed_text(template)

        # Search
        return self.search_similar_capsules(
            query_embedding=query_embedding.tolist(),
            top_k=top_k,
            **kwargs
        )

    def get_related_capsules(
        self,
        capsule_id: str,
        capsule_service,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Find capsules related to a given capsule

        Args:
            capsule_id: Source capsule ID
            capsule_service: CapsuleService instance
            top_k: Number of related capsules

        Returns:
            List of related capsules
        """
        # Get source capsule
        from uuid import UUID
        capsule = capsule_service.get_capsule(UUID(capsule_id))
        if not capsule or not capsule.embedding_vector_id:
            return []

        # Get embedding from Milvus
        # TODO: Implement get_embedding method in VectorStorageClient
        # For now, return empty list
        return []
