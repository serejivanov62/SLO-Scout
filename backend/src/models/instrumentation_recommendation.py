"""
InstrumentationRecommendation model per data-model.md
"""
from sqlalchemy import Column, String, Enum, Text, Numeric, TIMESTAMP, UUID as _unused, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from .base import Base, UUID


class RecommendationType(str, enum.Enum):
    ENABLE_RUM = "enable_rum"
    ADD_TRACING = "add_tracing"
    FIX_CARDINALITY = "fix_cardinality"
    ADD_REQUEST_ID = "add_request_id"


class ImplementationCost(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationPriority(str, enum.Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    NICE_TO_HAVE = "nice_to_have"


class RecommendationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"


class InstrumentationRecommendation(Base):
    """
    A suggested change to improve telemetry quality

    Per data-model.md InstrumentationRecommendation entity
    """
    __tablename__ = "instrumentation_recommendation"

    recommendation_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    service_id = Column(UUID(), ForeignKey("service.service_id", ondelete="CASCADE"), nullable=False)
    recommendation_type = Column(Enum(RecommendationType), nullable=False)
    description = Column(Text, nullable=False)
    code_snippet = Column(Text, nullable=True)
    expected_confidence_uplift = Column(Numeric(5, 2), nullable=False)  # 0-100
    implementation_cost = Column(Enum(ImplementationCost), nullable=False)
    priority = Column(Enum(RecommendationPriority), nullable=False)
    status = Column(Enum(RecommendationStatus), nullable=False, default=RecommendationStatus.PENDING)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    service = relationship("Service", back_populates="instrumentation_recommendations")

    # Constraints per data-model.md
    __table_args__ = ()  # Constraints disabled for SQLite compatibility

    def __repr__(self) -> str:
        return f"<InstrumentationRecommendation {self.recommendation_type} ({self.priority})>"
