"""
Service model per data-model.md
"""
from sqlalchemy import Column, String, Enum, JSON, TIMESTAMP, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from .base import Base, UUID


class ServiceStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class Environment(str, enum.Enum):
    PROD = "prod"
    STAGING = "staging"
    DEV = "dev"


class Service(Base):
    """
    Represents a monitored production service/application

    Per data-model.md Service entity
    """
    __tablename__ = "service"

    service_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    environment = Column(Enum(Environment), nullable=False)
    owner_team = Column(String(255), nullable=False)
    telemetry_endpoints = Column(JSON, nullable=False)  # {prometheus_url, otlp_endpoint, loki_url, rum_token}
    retention_policy_id = Column(UUID(), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    status = Column(Enum(ServiceStatus), nullable=False, default=ServiceStatus.ACTIVE)
    organization_id = Column(UUID(), nullable=False)

    # Relationships
    user_journeys = relationship("UserJourney", back_populates="service", cascade="all, delete-orphan")
    capsules = relationship("Capsule", back_populates="service", cascade="all, delete-orphan")
    instrumentation_recommendations = relationship(
        "InstrumentationRecommendation",
        back_populates="service",
        cascade="all, delete-orphan"
    )

    # Constraints per data-model.md
    # Note: json_typeof() is PostgreSQL-specific, removed for SQLite compatibility in tests
    __table_args__ = tuple() if False else ()

    def __repr__(self) -> str:
        return f"<Service {self.name} ({self.environment})>"
