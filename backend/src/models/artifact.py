"""
Artifact model per data-model.md
"""
from sqlalchemy import Column, String, Enum, Text, JSON, Integer, TIMESTAMP, UUID as _unused, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from .base import Base, UUID


class ArtifactType(str, enum.Enum):
    PROMETHEUS_RECORDING = "prometheus_recording"
    PROMETHEUS_ALERT = "prometheus_alert"
    GRAFANA_DASHBOARD = "grafana_dashboard"
    RUNBOOK = "runbook"


class ValidationStatus(str, enum.Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DeploymentStatus(str, enum.Enum):
    PENDING = "pending"
    DEPLOYED = "deployed"
    ROLLBACK = "rollback"


class Artifact(Base):
    """
    A generated operational output (Prometheus rule, Grafana panel, runbook)

    Per data-model.md Artifact entity
    """
    __tablename__ = "artifact"

    artifact_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    slo_id = Column(UUID(), ForeignKey("slo.slo_id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(Enum(ArtifactType), nullable=False)
    content = Column(Text, nullable=False)  # YAML or JSON
    validation_status = Column(Enum(ValidationStatus), nullable=False, default=ValidationStatus.PENDING)
    validation_errors = Column(JSON, nullable=True)
    approval_status = Column(Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING)
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(TIMESTAMP(timezone=True), nullable=True)
    deployment_status = Column(Enum(DeploymentStatus), nullable=False, default=DeploymentStatus.PENDING)
    deployment_pr_url = Column(String(500), nullable=True)
    deployed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    slo = relationship("SLO", back_populates="artifacts")

    def __repr__(self) -> str:
        return f"<Artifact {self.artifact_type} v{self.version} ({self.approval_status})>"
