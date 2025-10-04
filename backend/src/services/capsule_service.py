"""
Capsule persistence service per T078
Saves Capsule to TimescaleDB + samples to S3 + embedding to Milvus
Transactional across stores
"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..models.capsule import Capsule
from ..storage.blob_storage import BlobStorageClient
from ..storage.vector_storage import VectorStorageClient
from ..storage.timescale_manager import get_timescale_manager


class CapsuleService:
    """
    Service for persisting capsules across multiple storage backends

    Per data-model.md:
    - Metadata: TimescaleDB (fast queries)
    - Samples: S3/MinIO (JSONL.gz)
    - Embedding: Milvus/pgvector (similarity search)
    """

    def __init__(
        self,
        blob_storage: BlobStorageClient,
        vector_storage: VectorStorageClient
    ):
        self.blob_storage = blob_storage
        self.vector_storage = vector_storage
        self.db_manager = get_timescale_manager()

    def save_capsule(
        self,
        fingerprint_hash: str,
        template: str,
        count: int,
        severity_distribution: dict,
        samples: List[dict],
        service_id: UUID,
        first_seen_at: int,
        last_seen_at: int,
        time_bucket: int,
        embedding: Optional[List[float]] = None,
        redaction_applied: bool = False
    ) -> Capsule:
        """
        Save capsule to all storage backends (transactional)

        Args:
            fingerprint_hash: SHA256 hash
            template: Normalized log template
            count: Occurrence count
            severity_distribution: {DEBUG: count, INFO: count, ...}
            samples: List of sample events (max 10)
            service_id: Service UUID
            first_seen_at: Timestamp in ms
            last_seen_at: Timestamp in ms
            time_bucket: Aggregation window start in ms
            embedding: Optional embedding vector
            redaction_applied: PII redaction status

        Returns:
            Saved Capsule instance

        Raises:
            Exception: If transactional save fails
        """
        capsule = None
        s3_key = None
        embedding_id = None

        try:
            # Step 1: Save samples to S3
            s3_key = f"capsules/{fingerprint_hash}/{time_bucket}/samples.jsonl.gz"
            self.blob_storage.upload_sample(s3_key, samples, compress=True)

            # Step 2: Save embedding to Milvus (if provided)
            if embedding is not None and redaction_applied:
                embedding_id = self.vector_storage.index_embedding(
                    capsule_id="",  # Will update after DB insert
                    fingerprint_hash=fingerprint_hash,
                    service_name="",  # TODO: Get from service_id
                    environment="prod",  # TODO: Get from service
                    severity=list(severity_distribution.keys())[0] if severity_distribution else "INFO",
                    time_bucket=time_bucket,
                    embedding=embedding
                )

            # Step 3: Save metadata to TimescaleDB
            with self.db_manager.get_session() as session:
                capsule = Capsule(
                    fingerprint_hash=fingerprint_hash,
                    template=template,
                    count=count,
                    severity_distribution=severity_distribution,
                    sample_array=samples,
                    embedding_vector_id=embedding_id,
                    service_id=service_id,
                    first_seen_at=first_seen_at,
                    last_seen_at=last_seen_at,
                    time_bucket=time_bucket,
                    redaction_applied=redaction_applied
                )
                session.add(capsule)
                session.flush()  # Get capsule_id

                # Update embedding with capsule_id
                if embedding_id and embedding is not None:
                    # Re-index with correct capsule_id
                    self.vector_storage.delete_embedding(embedding_id)
                    self.vector_storage.index_embedding(
                        capsule_id=str(capsule.capsule_id),
                        fingerprint_hash=fingerprint_hash,
                        service_name="",  # TODO
                        environment="prod",
                        severity="INFO",
                        time_bucket=time_bucket,
                        embedding=embedding
                    )

                session.commit()

            return capsule

        except Exception as e:
            # Rollback all changes
            if s3_key:
                try:
                    self.blob_storage.delete_blob(s3_key)
                except:
                    pass

            if embedding_id:
                try:
                    self.vector_storage.delete_embedding(embedding_id)
                except:
                    pass

            raise Exception(f"Failed to save capsule: {e}")

    def get_capsule(self, capsule_id: UUID) -> Optional[Capsule]:
        """Get capsule by ID"""
        with self.db_manager.get_session() as session:
            return session.query(Capsule).filter(
                Capsule.capsule_id == capsule_id
            ).first()

    def get_capsules_by_fingerprint(
        self,
        fingerprint_hash: str,
        service_id: UUID,
        limit: int = 10
    ) -> List[Capsule]:
        """Get capsules by fingerprint hash"""
        with self.db_manager.get_session() as session:
            return session.query(Capsule).filter(
                Capsule.fingerprint_hash == fingerprint_hash,
                Capsule.service_id == service_id
            ).order_by(
                Capsule.time_bucket.desc()
            ).limit(limit).all()
