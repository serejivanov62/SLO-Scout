"""
Service model - Registry of monitored services with telemetry connection details
"""
from datetime import datetime
from typing import Optional
from uuid import UUID as PyUUID, uuid4
import enum

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Index,
    Enum,
    CheckConstraint,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from src.models.base import Base, UUID


class EnvironmentEnum(str, enum.Enum):
    """Service environment enum"""
    PROD = "prod"
    STAGING = "staging"
    DEV = "dev"


class ServiceStatusEnum(str, enum.Enum):
    """Service status enum"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class Service(Base):
    """
    Service model representing monitored services with telemetry connection details.

    Attributes:
        id: UUID primary key
        name: Service name (unique per environment)
        environment: Service environment (prod/staging/dev)
        owner_team: Team responsible for the service
        telemetry_endpoints: JSONB mapping of telemetry system endpoints
        label_mappings: JSONB mapping of labels for each telemetry system
        created_at: Timestamp when service was created
        updated_at: Timestamp when service was last updated
        status: Service status (active/inactive/archived)
    """
    __tablename__ = "services"

    # Columns
    id: PyUUID = Column(
        UUID,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="UUID v4 primary key"
    )

    name: str = Column(
        String(255),
        nullable=False,
        comment="Service name"
    )

    environment: EnvironmentEnum = Column(
        Enum(EnvironmentEnum, name="environment_enum", create_type=False),
        nullable=False,
        comment="Service environment"
    )

    owner_team: str = Column(
        String(255),
        nullable=False,
        comment="Team responsible for the service"
    )

    telemetry_endpoints: dict = Column(
        JSONB,
        nullable=False,
        comment="Telemetry system endpoints (prometheus, loki, jaeger)"
    )

    label_mappings: dict = Column(
        JSONB,
        nullable=False,
        comment="Label mappings for each telemetry system"
    )

    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Timestamp when service was created"
    )

    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Timestamp when service was last updated"
    )

    status: ServiceStatusEnum = Column(
        Enum(ServiceStatusEnum, name="status_enum", create_type=False),
        nullable=False,
        server_default="active",
        comment="Service status"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("name", "environment", name="uq_services_name_environment"),
        Index("idx_services_status_environment", "status", "environment"),
    )

    # Relationships
    telemetry_events = relationship(
        "TelemetryEvent",
        back_populates="service",
        cascade="all, delete-orphan"
    )

    capsules = relationship(
        "Capsule",
        back_populates="service",
        cascade="all, delete-orphan"
    )

    user_journeys = relationship(
        "UserJourney",
        back_populates="service",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Service(id={self.id}, name={self.name}, environment={self.environment})>"
