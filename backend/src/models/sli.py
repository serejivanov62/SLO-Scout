"""
SLI model - Service Level Indicators with approval workflow
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
    Boolean,
    text,
)
from sqlalchemy.orm import relationship

from src.models.base import Base, UUID


class SLI(Base):
    """
    SLI model for recommended Service Level Indicators.

    Represents AI-recommended SLIs with approval workflow for human validation.

    Attributes:
        sli_id: UUID primary key
        journey_id: Foreign key to user_journeys table
        name: SLI name
        description: SLI description
        promql_query: PromQL query for the SLI
        confidence_score: AI confidence score (0.0-1.0)
        approved: Whether SLI has been approved
        approved_by: Username/email of approver
        approved_at: Timestamp when approved
        created_at: Timestamp when SLI was created
    """
    __tablename__ = "slis"

    # Primary key
    sli_id: PyUUID = Column(
        UUID,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="UUID v4 primary key"
    )

    # Foreign keys
    journey_id: PyUUID = Column(
        UUID,
        ForeignKey("user_journeys.journey_id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key to user_journeys table"
    )

    # Data columns
    name: str = Column(
        String(255),
        nullable=False,
        comment="SLI name"
    )

    description: Optional[str] = Column(
        Text,
        nullable=True,
        comment="SLI description"
    )

    promql_query: str = Column(
        Text,
        nullable=False,
        comment="PromQL query for the SLI"
    )

    confidence_score: Decimal = Column(
        Numeric(4, 3),
        nullable=False,
        comment="AI confidence score (0.000-1.000)"
    )

    # Approval workflow columns
    approved: bool = Column(
        Boolean,
        nullable=False,
        server_default=text("FALSE"),
        comment="Whether SLI has been approved"
    )

    approved_by: Optional[str] = Column(
        String(255),
        nullable=True,
        comment="Username/email of approver"
    )

    approved_at: Optional[datetime] = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when approved"
    )

    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Timestamp when SLI was created"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_confidence_score_range"
        ),
        CheckConstraint(
            "(approved = TRUE AND approved_by IS NOT NULL AND approved_at IS NOT NULL) OR (approved = FALSE)",
            name="ck_approval_consistency"
        ),
        Index("idx_slis_journey_approved", "journey_id", "approved"),
        Index("idx_slis_approved_by", "approved_by", postgresql_where=text("approved_by IS NOT NULL")),
        Index("idx_slis_confidence", text("confidence_score DESC")),
        Index("idx_slis_created", text("created_at DESC")),
    )

    # Relationships
    user_journey = relationship("UserJourney", back_populates="slis")
    slos = relationship(
        "SLO",
        back_populates="sli",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        approval_status = "approved" if self.approved else "pending"
        return f"<SLI(id={self.sli_id}, name={self.name}, status={approval_status})>"
