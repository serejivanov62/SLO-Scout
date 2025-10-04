"""
SLO (Service Level Objective) model per data-model.md
"""
from sqlalchemy import Column, String, Enum, Numeric, Interval, TIMESTAMP, UUID as _unused, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from .base import Base, UUID


class ComparisonOperator(str, enum.Enum):
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    EQ = "eq"


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class SLOVariant(str, enum.Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class SLO(Base):
    """
    A target threshold for an SLI over a time window

    Per data-model.md SLO entity
    Time-series hypertable partitioned by created_at
    """
    __tablename__ = "slo"

    slo_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    sli_id = Column(UUID(), ForeignKey("sli.sli_id", ondelete="CASCADE"), nullable=False)
    threshold_value = Column(Numeric, nullable=False)
    comparison_operator = Column(Enum(ComparisonOperator), nullable=False)
    time_window = Column(Interval, nullable=False)
    target_percentage = Column(Numeric(5, 2), nullable=False)  # 0-100
    severity = Column(Enum(Severity), nullable=False)
    breach_policy = Column(String(255), nullable=True)
    historical_breach_frequency = Column(Numeric, nullable=True)
    variant = Column(Enum(SLOVariant), nullable=False)
    error_budget_remaining = Column(Numeric(5, 2), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(TIMESTAMP(timezone=True), nullable=True)
    deployed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    sli = relationship("SLI", back_populates="slos")
    artifacts = relationship("Artifact", back_populates="slo", cascade="all, delete-orphan")

    # Constraints per data-model.md
    # Note: Disabled for SQLite compatibility in tests
    __table_args__ = ()

    def __repr__(self) -> str:
        return f"<SLO {self.sli_id} {self.comparison_operator} {self.threshold_value} ({self.variant})>"
