"""
Capsule model per data-model.md
"""
from sqlalchemy import Column, String, BigInteger, JSON, Boolean, TIMESTAMP, UUID as _unused, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from .base import Base, UUID


class Capsule(Base):
    """
    A compressed representation of a log/trace fingerprint

    Per data-model.md Capsule entity
    Time-series hypertable partitioned by time_bucket
    """
    __tablename__ = "capsule"

    capsule_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    fingerprint_hash = Column(String(64), nullable=False)  # SHA256
    template = Column(String, nullable=False)  # Normalized pattern
    count = Column(BigInteger, nullable=False)
    severity_distribution = Column(JSON, nullable=False)  # {DEBUG: count, INFO: count, ...}
    sample_array = Column(JSON, nullable=False)  # Max 10 samples
    embedding_vector_id = Column(String(255), nullable=True)  # Milvus ID
    service_id = Column(UUID(), ForeignKey("service.service_id", ondelete="CASCADE"), nullable=False)
    first_seen_at = Column(TIMESTAMP(timezone=True), nullable=False)
    last_seen_at = Column(TIMESTAMP(timezone=True), nullable=False)
    time_bucket = Column(TIMESTAMP(timezone=True), nullable=False)  # Hypertable partition key
    redaction_applied = Column(Boolean, nullable=False, default=False)

    # Relationships
    service = relationship("Service", back_populates="capsules")
    evidence_pointers = relationship("EvidencePointer", back_populates="capsule")

    # Constraints per data-model.md
    __table_args__ = ()  # Constraints disabled for SQLite compatibility

    def __repr__(self) -> str:
        return f"<Capsule {self.fingerprint_hash[:8]}... count={self.count}>"
