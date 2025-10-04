"""
Milvus vector DB client per T039
"""
from pymilvus import connections, Collection, utility
from typing import List, Dict, Optional
import numpy as np


class VectorStorageClient:
    """Milvus client for capsule embeddings"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        collection_name: str = "capsules"
    ):
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.collection: Optional[Collection] = None

        # Connect to Milvus
        connections.connect(
            alias="default",
            host=host,
            port=port
        )

        # Load collection
        if utility.has_collection(collection_name):
            self.collection = Collection(collection_name)
            self.collection.load()

    def index_embedding(
        self,
        capsule_id: str,
        fingerprint_hash: str,
        service_name: str,
        environment: str,
        severity: str,
        time_bucket: int,
        embedding: List[float]
    ) -> str:
        """
        Index capsule embedding in Milvus

        Args:
            capsule_id: UUID from TimescaleDB
            fingerprint_hash: SHA256 hash
            service_name: Service name for filtering
            environment: prod/staging/dev
            severity: Log severity
            time_bucket: Timestamp in milliseconds
            embedding: 384-dim vector (MiniLM) or 1536-dim (OpenAI)

        Returns:
            Insert ID
        """
        if not self.collection:
            raise Exception(f"Collection {self.collection_name} not found")

        data = [{
            "capsule_id": capsule_id,
            "fingerprint_hash": fingerprint_hash,
            "service_name": service_name,
            "environment": environment,
            "severity": severity,
            "time_bucket": time_bucket,
            "embedding": embedding
        }]

        result = self.collection.insert(data)
        self.collection.flush()

        return result.primary_keys[0]

    def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        service_name: Optional[str] = None,
        environment: Optional[str] = None,
        time_range: Optional[tuple] = None
    ) -> List[Dict]:
        """
        Search for similar capsules using vector similarity

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            service_name: Filter by service (optional)
            environment: Filter by environment (optional)
            time_range: (start_ms, end_ms) timestamp range (optional)

        Returns:
            List of matching capsules with scores
        """
        if not self.collection:
            raise Exception(f"Collection {self.collection_name} not found")

        # Build filter expression
        filter_expr = []
        if service_name:
            filter_expr.append(f'service_name == "{service_name}"')
        if environment:
            filter_expr.append(f'environment == "{environment}"')
        if time_range:
            start_ms, end_ms = time_range
            filter_expr.append(f"time_bucket >= {start_ms} && time_bucket <= {end_ms}")

        expr = " && ".join(filter_expr) if filter_expr else None

        # Search parameters per research.md: HNSW with ef=100
        search_params = {
            "metric_type": "IP",  # Inner Product (cosine similarity)
            "params": {"ef": 100}
        }

        results = self.collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=["capsule_id", "fingerprint_hash", "service_name", "severity", "time_bucket"]
        )

        # Format results
        matches = []
        for hits in results:
            for hit in hits:
                matches.append({
                    "capsule_id": hit.entity.get("capsule_id"),
                    "fingerprint_hash": hit.entity.get("fingerprint_hash"),
                    "service_name": hit.entity.get("service_name"),
                    "severity": hit.entity.get("severity"),
                    "time_bucket": hit.entity.get("time_bucket"),
                    "score": hit.score,
                    "distance": hit.distance
                })

        return matches

    def delete_embedding(self, capsule_id: str) -> None:
        """
        Delete embedding by capsule ID

        Args:
            capsule_id: Capsule UUID
        """
        if not self.collection:
            raise Exception(f"Collection {self.collection_name} not found")

        self.collection.delete(f'capsule_id == "{capsule_id}"')
        self.collection.flush()

    def get_stats(self) -> Dict:
        """Get collection statistics"""
        if not self.collection:
            raise Exception(f"Collection {self.collection_name} not found")

        return {
            "num_entities": self.collection.num_entities,
            "collection_name": self.collection_name,
            "schema": self.collection.schema
        }
