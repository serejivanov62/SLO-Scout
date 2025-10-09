"""
SLO model - Service Level Objectives with thresholds
"""
from datetime import datetime
from typing import Optional
from uuid import UUID as PyUUID
from decimal import Decimal
import enum

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Index,
    ForeignKey,
    CheckConstraint,
    Numeric,
    Enum,
    text,
)
from sqlalchemy.orm import relationship

from src.models.base import Base, UUID


class ThresholdVariantEnum(str, enum.Enum):
    """SLO threshold variant enum"""
    CONSERVATIVE = "conservative"  # Higher error budget thresholds (slower alerts)
    BALANCED = "balanced"          # Standard thresholds (Google SRE defaults)
    AGGRESSIVE = "aggressive"      # Lower thresholds (faster alerts, more noise)


class SLO(Base):
    """
    SLO model for Service Level Objectives with error budget thresholds.

    Attributes:
        slo_id: UUID primary key
        sli_id: Foreign key to slis table
        name: SLO name
        target_percentage: Target percentage (0.00-100.00)
        time_window: Time window for SLO (e.g., "30d", "7d", "24h")
        threshold_variant: Alert threshold variant
        created_at: Timestamp when SLO was created
    """
    __tablename__ = "slos"

    # Primary key
    slo_id: PyUUID = Column(
        UUID,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="UUID v4 primary key"
    )

    # Foreign keys
    sli_id: PyUUID = Column(
        UUID,
        ForeignKey("slis.sli_id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key to slis table"
    )

    # Data columns
    name: str = Column(
        String(255),
        nullable=False,
        comment="SLO name"
    )

    target_percentage: Decimal = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Target percentage (0.00-100.00)"
    )

    time_window: str = Column(
        String(50),
        nullable=False,
        comment="Time window for SLO (e.g., '30d', '7d', '24h')"
    )

    threshold_variant: ThresholdVariantEnum = Column(
        Enum(ThresholdVariantEnum, name="threshold_variant_enum", create_type=False),
        nullable=False,
        server_default="balanced",
        comment="Alert threshold variant"
    )

    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Timestamp when SLO was created"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "target_percentage >= 0 AND target_percentage <= 100",
            name="ck_target_percentage_range"
        ),
        Index("idx_slos_sli", "sli_id"),
        Index("idx_slos_threshold_variant", "threshold_variant"),
        Index("idx_slos_created", text("created_at DESC")),
    )

    # Relationships
    sli = relationship("SLI", back_populates="slos")
    artifacts = relationship(
        "Artifact",
        back_populates="slo",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SLO(id={self.slo_id}, name={self.name}, target={self.target_percentage}%)>"
