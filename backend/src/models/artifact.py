"""
Artifact model - Generated Prometheus/Grafana configurations
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
    Text,
    Index,
    ForeignKey,
    CheckConstraint,
    Numeric,
    Enum,
    text,
)
from sqlalchemy.orm import relationship

from src.models.base import Base, UUID


class ArtifactTypeEnum(str, enum.Enum):
    """Artifact type enum"""
    PROMETHEUS_RULE = "prometheus_rule"
    GRAFANA_DASHBOARD = "grafana_dashboard"
    RUNBOOK = "runbook"


class ArtifactStatusEnum(str, enum.Enum):
    """Artifact status enum"""
    DRAFT = "draft"
    DEPLOYED = "deployed"
    ROLLED_BACK = "rolled_back"


class Artifact(Base):
    """
    Artifact model for generated Prometheus/Grafana configurations.

    Represents auto-generated monitoring artifacts (rules, dashboards, runbooks)
    with deployment tracking.

    Attributes:
        artifact_id: UUID primary key
        slo_id: Foreign key to slos table
        artifact_type: Type of artifact
        content: YAML/JSON configuration content
        confidence_score: AI confidence score (0.0-1.0)
        status: Deployment status
        pr_url: GitHub PR URL for the deployment
        deployed_at: Timestamp when deployed
        created_at: Timestamp when artifact was created
    """
    __tablename__ = "artifacts"

    # Primary key
    artifact_id: PyUUID = Column(
        UUID,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="UUID v4 primary key"
    )

    # Foreign keys
    slo_id: PyUUID = Column(
        UUID,
        ForeignKey("slos.slo_id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key to slos table"
    )

    # Data columns
    artifact_type: ArtifactTypeEnum = Column(
        Enum(ArtifactTypeEnum, name="artifact_type_enum", create_type=False),
        nullable=False,
        comment="Type of artifact"
    )

    content: str = Column(
        Text,
        nullable=False,
        comment="YAML/JSON configuration content"
    )

    confidence_score: Decimal = Column(
        Numeric(4, 3),
        nullable=False,
        comment="AI confidence score (0.000-1.000)"
    )

    status: ArtifactStatusEnum = Column(
        Enum(ArtifactStatusEnum, name="artifact_status_enum", create_type=False),
        nullable=False,
        server_default="draft",
        comment="Deployment status"
    )

    pr_url: Optional[str] = Column(
        String(512),
        nullable=True,
        comment="GitHub PR URL for the deployment"
    )

    deployed_at: Optional[datetime] = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when deployed"
    )

    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Timestamp when artifact was created"
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_confidence_score_range"
        ),
        CheckConstraint(
            "(status = 'deployed' AND deployed_at IS NOT NULL) OR (status != 'deployed')",
            name="ck_deployment_consistency"
        ),
        Index("idx_artifacts_slo_status", "slo_id", "status"),
        Index("idx_artifacts_status_deployed", "status", text("deployed_at DESC")),
        Index("idx_artifacts_type", "artifact_type"),
        Index("idx_artifacts_created", text("created_at DESC")),
    )

    # Relationships
    slo = relationship("SLO", back_populates="artifacts")

    def __repr__(self) -> str:
        return f"<Artifact(id={self.artifact_id}, type={self.artifact_type}, status={self.status})>"
