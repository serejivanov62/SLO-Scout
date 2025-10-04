"""
Capsule retrieval service per T082
Fetches capsule metadata from TimescaleDB
Fetches samples from S3
Combines into Evidence structure
"""
from typing import List, Dict, Optional
from uuid import UUID

from ..services.capsule_service import CapsuleService
from ..storage.blob_storage import BlobStorageClient
from ..models.capsule import Capsule


class CapsuleRetrievalService:
    """
    Service for retrieving complete capsule data

    Combines:
    - Metadata from TimescaleDB
    - Samples from S3
    - Embeddings from Milvus (via capsule_service)
    """

    def __init__(
        self,
        capsule_service: CapsuleService,
        blob_storage: BlobStorageClient
    ):
        self.capsule_service = capsule_service
        self.blob_storage = blob_storage

    def get_capsule_with_samples(self, capsule_id: UUID) -> Optional[Dict]:
        """
        Get complete capsule data including samples

        Args:
            capsule_id: Capsule UUID

        Returns:
            Dictionary with capsule metadata and samples:
            {
                "capsule_id": "uuid",
                "fingerprint_hash": "hash",
                "template": "User {USER_ID} logged in",
                "count": 1234,
                "severity_distribution": {"INFO": 1234},
                "samples": [{"event_id": "...", ...}, ...],
                "first_seen_at": 1699200000000,
                "last_seen_at": 1699203600000,
                "time_bucket": 1699200000000,
                "redaction_applied": true
            }
        """
        # Get metadata from TimescaleDB
        capsule = self.capsule_service.get_capsule(capsule_id)
        if not capsule:
            return None

        # Get samples from S3
        samples = self._fetch_samples(capsule)

        # Build response
        return {
            "capsule_id": str(capsule.capsule_id),
            "fingerprint_hash": capsule.fingerprint_hash,
            "template": capsule.template,
            "count": capsule.count,
            "severity_distribution": capsule.severity_distribution,
            "samples": samples,
            "first_seen_at": capsule.first_seen_at,
            "last_seen_at": capsule.last_seen_at,
            "time_bucket": capsule.time_bucket,
            "redaction_applied": capsule.redaction_applied,
            "embedding_vector_id": capsule.embedding_vector_id
        }

    def get_capsules_batch(self, capsule_ids: List[UUID]) -> List[Dict]:
        """
        Get multiple capsules in batch

        Args:
            capsule_ids: List of capsule UUIDs

        Returns:
            List of capsule dictionaries
        """
        return [
            self.get_capsule_with_samples(capsule_id)
            for capsule_id in capsule_ids
            if self.get_capsule_with_samples(capsule_id) is not None
        ]

    def get_evidence_for_sli(
        self,
        capsule_ids: List[UUID],
        include_samples: bool = True
    ) -> List[Dict]:
        """
        Get capsules formatted as evidence for SLI recommendations

        Args:
            capsule_ids: List of capsule UUIDs (from vector search)
            include_samples: Whether to include sample events

        Returns:
            List of evidence dictionaries:
            [
                {
                    "capsule_id": "uuid",
                    "template": "normalized template",
                    "count": 1234,
                    "confidence_contribution": 0.85,
                    "samples": [...] if include_samples else []
                },
                ...
            ]
        """
        evidence = []

        for capsule_id in capsule_ids:
            capsule_data = self.get_capsule_with_samples(capsule_id)
            if capsule_data:
                evidence_item = {
                    "capsule_id": capsule_data["capsule_id"],
                    "template": capsule_data["template"],
                    "count": capsule_data["count"],
                    "confidence_contribution": self._calculate_confidence(capsule_data),
                    "timestamp": capsule_data["time_bucket"]
                }

                if include_samples:
                    evidence_item["samples"] = capsule_data["samples"]

                evidence.append(evidence_item)

        return evidence

    def _fetch_samples(self, capsule: Capsule) -> List[Dict]:
        """
        Fetch samples from S3

        Args:
            capsule: Capsule ORM instance

        Returns:
            List of sample events
        """
        # Check if samples are stored inline or in S3
        if capsule.sample_array and len(capsule.sample_array) > 0:
            # Samples stored inline in TimescaleDB
            return capsule.sample_array

        # Samples stored in S3
        s3_key = f"capsules/{capsule.fingerprint_hash}/{capsule.time_bucket}/samples.jsonl.gz"
        try:
            return self.blob_storage.download_sample(s3_key)
        except Exception as e:
            # Fallback to empty list if S3 fetch fails
            return []

    def _calculate_confidence(self, capsule_data: Dict) -> float:
        """
        Calculate confidence contribution for this capsule

        Based on:
        - Occurrence count (higher = more confident)
        - Recency (more recent = more confident)
        - Redaction status (redacted = more confident)

        Returns:
            Confidence score (0-100)
        """
        # Simple heuristic: log(count) * 10, capped at 100
        import math
        count = capsule_data['count']
        confidence = min(100, math.log10(max(1, count)) * 25)

        # Boost if redaction applied
        if capsule_data.get('redaction_applied'):
            confidence *= 1.1

        return min(100, confidence)
