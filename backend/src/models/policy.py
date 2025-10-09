"""
Policy model - Deployment safety rules
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
    CheckConstraint,
    Numeric,
    Boolean,
    UniqueConstraint,
    text,
)

from src.models.base import Base, UUID


class Policy(Base):
    """
    Policy model for deployment safety rules.

    Defines guardrails for automatic artifact deployment based on blast radius
    and other safety criteria.

    Attributes:
        policy_id: UUID primary key
        name: Unique policy name
        description: Policy description
        blast_radius_threshold: Maximum blast radius allowed (0.00-1.00)
        enabled: Whether policy is active
        created_at: Timestamp when policy was created
        updated_at: Timestamp when policy was last updated
    """
    __tablename__ = "policies"

    # Primary key
    policy_id: PyUUID = Column(
        UUID,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="UUID v4 primary key"
    )

    # Data columns
    name: str = Column(
        String(255),
        nullable=False,
        unique=True,
        comment="Unique policy name"
    )

    description: Optional[str] = Column(
        Text,
        nullable=True,
        comment="Policy description"
    )

    blast_radius_threshold: Decimal = Column(
        Numeric(3, 2),
        nullable=False,
        comment="Maximum blast radius allowed (0.00-1.00)"
    )

    enabled: bool = Column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
        comment="Whether policy is active"
    )

    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Timestamp when policy was created"
    )

    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Timestamp when policy was last updated"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "blast_radius_threshold >= 0 AND blast_radius_threshold <= 1",
            name="ck_blast_radius_threshold_range"
        ),
        Index("idx_policies_enabled", "enabled", postgresql_where=text("enabled = true")),
    )

    def __repr__(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        return f"<Policy(id={self.policy_id}, name={self.name}, status={status})>"
