"""
Capsule model - Fingerprinted event aggregations (TimescaleDB Hypertable)
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID as PyUUID

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Integer,
    Index,
    ForeignKey,
    CheckConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from src.models.base import Base, UUID


class Capsule(Base):
    """
    Capsule model for fingerprinted event aggregations.

    This is a TimescaleDB hypertable partitioned by window_start with 1-hour chunks.
    Used for journey discovery through event pattern analysis.

    Attributes:
        capsule_id: UUID capsule identifier (part of composite PK)
        service_id: Foreign key to services table
        journey_id: Foreign key to user_journeys table (optional)
        fingerprint_hash: SHA256 hash for deduplication
        template: Normalized event pattern template
        event_count: Number of events in this capsule
        window_start: Aggregation window start time (part of composite PK)
        window_end: Aggregation window end time
        sample_events: Array of event_id references
    """
    __tablename__ = "capsules"

    # Composite primary key for hypertable partitioning
    capsule_id: PyUUID = Column(
        UUID,
        primary_key=True,
        nullable=False,
        comment="UUID v4 capsule identifier"
    )

    window_start: datetime = Column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        comment="Aggregation window start time (partition key)"
    )

    # Foreign keys
    service_id: PyUUID = Column(
        UUID,
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key to services table"
    )

    journey_id: Optional[PyUUID] = Column(
        UUID,
        ForeignKey("user_journeys.journey_id", ondelete="SET NULL"),
        nullable=True,
        comment="Foreign key to user_journeys table"
    )

    # Data columns
    fingerprint_hash: str = Column(
        String(64),
        nullable=False,
        comment="SHA256 hash for deduplication"
    )

    template: str = Column(
        Text,
        nullable=False,
        comment="Normalized event pattern template"
    )

    event_count: int = Column(
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="Number of events in this capsule"
    )

    window_end: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Aggregation window end time"
    )

    sample_events: List[str] = Column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
        comment="Array of event_id references"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("window_end > window_start", name="ck_window_end_after_start"),
        CheckConstraint("event_count > 0", name="ck_event_count_positive"),
        Index("idx_capsules_fingerprint", "fingerprint_hash"),
        Index("idx_capsules_service_journey", "service_id", "journey_id"),
        Index("idx_capsules_service_window", "service_id", text("window_start DESC")),
        Index(
            "idx_capsules_journey_window",
            "journey_id",
            text("window_start DESC"),
            postgresql_where=text("journey_id IS NOT NULL")
        ),
    )

    # Relationships
    service = relationship("Service", back_populates="capsules")
    user_journey = relationship("UserJourney", back_populates="capsules")

    def __repr__(self) -> str:
        return f"<Capsule(id={self.capsule_id}, fingerprint={self.fingerprint_hash[:8]}, window_start={self.window_start})>"
