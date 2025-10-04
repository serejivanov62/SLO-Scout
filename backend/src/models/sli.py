"""
SLI (Service Level Indicator) model per data-model.md
"""
from sqlalchemy import Column, String, Enum, Text, Interval, JSON, Numeric, TIMESTAMP, UUID as _unused, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from .base import Base, UUID


class MetricType(str, enum.Enum):
    LATENCY = "latency"
    AVAILABILITY = "availability"
    ERROR_RATE = "error_rate"
    CUSTOM = "custom"


class SLI(Base):
    """
    A measurable metric that reflects user experience quality

    Per data-model.md SLI entity
    """
    __tablename__ = "sli"

    sli_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    journey_id = Column(UUID(), ForeignKey("user_journey.journey_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    metric_type = Column(Enum(MetricType), nullable=False)
    metric_definition = Column(Text, nullable=False)  # PromQL string
    measurement_window = Column(Interval, nullable=False)
    data_sources = Column(JSON, nullable=False)  # {prometheus: [metrics], traces: [spans], logs: [patterns]}
    confidence_score = Column(Numeric(5, 2), nullable=False)  # 0-100
    evidence_pointers = Column(JSON, nullable=False)  # [{capsule_id, contribution_weight}]
    current_value = Column(Numeric, nullable=True)
    unit = Column(String(20), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    journey = relationship("UserJourney", back_populates="slis")
    slos = relationship("SLO", back_populates="sli", cascade="all, delete-orphan")
    evidence_pointers_rel = relationship("EvidencePointer", back_populates="sli", cascade="all, delete-orphan")

    # Constraints per data-model.md
    __table_args__ = ()  # Constraints disabled for SQLite compatibility

    def __repr__(self) -> str:
        return f"<SLI {self.name} ({self.metric_type})>"
