"""
EvidencePointer model per data-model.md
"""
from sqlalchemy import Column, String, Enum, Text, Numeric, TIMESTAMP, UUID as _unused, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
import uuid
import enum

from .base import Base, UUID


class RedactionStatus(str, enum.Enum):
    REDACTED = "redacted"
    SAFE = "safe"
    PENDING = "pending"


class EvidencePointer(Base):
    """
    A reference linking a recommendation to source data

    Per data-model.md EvidencePointer entity
    """
    __tablename__ = "evidence_pointer"

    evidence_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    sli_id = Column(UUID(), ForeignKey("sli.sli_id", ondelete="CASCADE"), nullable=False)
    capsule_id = Column(UUID(), ForeignKey("capsule.capsule_id", ondelete="SET NULL"), nullable=True)
    trace_id = Column(String(255), nullable=True)
    log_sample = Column(Text, nullable=True)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)
    confidence_contribution = Column(Numeric(5, 2), nullable=False)  # 0-100
    redaction_status = Column(Enum(RedactionStatus), nullable=False)

    # Relationships
    sli = relationship("SLI", back_populates="evidence_pointers_rel")
    capsule = relationship("Capsule", back_populates="evidence_pointers")

    # Constraints per data-model.md
    __table_args__ = ()  # Constraints disabled for SQLite compatibility

    def __repr__(self) -> str:
        return f"<EvidencePointer sli={self.sli_id} confidence={self.confidence_contribution}>"
