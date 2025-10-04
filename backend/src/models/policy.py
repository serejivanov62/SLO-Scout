"""
Policy model per data-model.md
"""
from sqlalchemy import Column, String, Enum, JSON, Boolean, TIMESTAMP, UUID as _unused, CheckConstraint
from sqlalchemy.sql import func
import uuid
import enum

from .base import Base, UUID


class PolicyScope(str, enum.Enum):
    GLOBAL = "global"
    ORGANIZATION = "organization"
    SERVICE = "service"


class EnforcementMode(str, enum.Enum):
    BLOCK = "block"
    WARN = "warn"
    AUDIT = "audit"


class Policy(Base):
    """
    A governance rule enforced by Policy Guard

    Per data-model.md Policy entity
    """
    __tablename__ = "policy"

    policy_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    scope = Column(Enum(PolicyScope), nullable=False)
    scope_id = Column(UUID(), nullable=True)  # FK to organization or service
    invariants = Column(JSON, nullable=False)  # {max_services_affected: 10, max_cost_impact_usd: 100}
    allowed_actions = Column(JSON, nullable=False)  # [artifact_deploy, auto_scale, rollback]
    enforcement_mode = Column(Enum(EnforcementMode), nullable=False)
    audit_required = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Constraints per data-model.md
    __table_args__ = ()  # Constraints disabled for SQLite compatibility

    def __repr__(self) -> str:
        return f"<Policy {self.name} ({self.enforcement_mode})>"
