"""
UserJourney model per data-model.md
"""
from sqlalchemy import Column, String, Integer, Numeric, JSON, TIMESTAMP, UUID as _unused, ForeignKey, CheckConstraint, ARRAY, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from .base import Base, UUID


class UserJourney(Base):
    """
    A critical path through the service identified from trace analysis and RUM data

    Per data-model.md UserJourney entity
    """
    __tablename__ = "user_journey"

    journey_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    service_id = Column(UUID(), ForeignKey("service.service_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    entry_point = Column(String(500), nullable=False)
    exit_point = Column(String(500), nullable=False)
    step_sequence = Column(JSON, nullable=False)  # [{span_name, duration_p50, error_rate}]
    traffic_volume_per_day = Column(Integer, nullable=True, default=0)  # Made nullable for SQLite
    confidence_score = Column(Numeric(5, 2), nullable=False)  # 0-100
    sample_trace_ids = Column(JSON, nullable=False)  # Changed from ARRAY to JSON for SQLite compatibility
    discovered_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    service = relationship("Service", back_populates="user_journeys")
    slis = relationship("SLI", back_populates="journey", cascade="all, delete-orphan")

    # Constraints per data-model.md
    __table_args__ = ()  # Constraints disabled for SQLite compatibility

    def __repr__(self) -> str:
        return f"<UserJourney {self.name} (confidence={self.confidence_score})>"
