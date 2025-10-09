"""
UserJourney model - Discovered user interaction patterns
"""
from datetime import datetime
from typing import Optional
from uuid import UUID as PyUUID
from decimal import Decimal

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Index,
    ForeignKey,
    CheckConstraint,
    Numeric,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from src.models.base import Base, UUID


class UserJourney(Base):
    """
    UserJourney model for discovered user interaction patterns.

    Represents end-to-end user flows discovered through telemetry analysis.

    Attributes:
        journey_id: UUID primary key
        service_id: Foreign key to services table
        name: Journey name
        description: Journey description
        entry_points: JSONB list of entry operations
        critical_path: JSONB sequence of steps with latency metrics
        confidence_score: AI confidence score (0.0-1.0)
        discovered_at: Timestamp when journey was discovered
    """
    __tablename__ = "user_journeys"

    # Primary key
    journey_id: PyUUID = Column(
        UUID,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="UUID v4 primary key"
    )

    # Foreign keys
    service_id: PyUUID = Column(
        UUID,
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key to services table"
    )

    # Data columns
    name: str = Column(
        String(255),
        nullable=False,
        comment="Journey name"
    )

    description: Optional[str] = Column(
        Text,
        nullable=True,
        comment="Journey description"
    )

    entry_points: dict = Column(
        JSONB,
        nullable=False,
        comment="List of entry operations"
    )

    critical_path: dict = Column(
        JSONB,
        nullable=False,
        comment="Sequence of steps with latency metrics"
    )

    confidence_score: Decimal = Column(
        Numeric(4, 3),
        nullable=False,
        comment="AI confidence score (0.000-1.000)"
    )

    discovered_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Timestamp when journey was discovered"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_confidence_score_range"
        ),
        Index("idx_journeys_service_discovered", "service_id", text("discovered_at DESC")),
        Index("idx_journeys_confidence", text("confidence_score DESC")),
    )

    # Relationships
    service = relationship("Service", back_populates="user_journeys")
    capsules = relationship(
        "Capsule",
        back_populates="user_journey"
    )
    slis = relationship(
        "SLI",
        back_populates="user_journey",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<UserJourney(id={self.journey_id}, name={self.name}, confidence={self.confidence_score})>"
