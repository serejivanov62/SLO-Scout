"""
TelemetryEvent model - Raw ingested telemetry (TimescaleDB Hypertable)
"""
from datetime import datetime
from typing import Optional
from uuid import UUID as PyUUID
import enum

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Index,
    Enum,
    ForeignKey,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from src.models.base import Base, UUID


class EventTypeEnum(str, enum.Enum):
    """Telemetry event type enum"""
    LOG = "log"
    TRACE = "trace"
    METRIC = "metric"


class SeverityEnum(str, enum.Enum):
    """Event severity enum"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TelemetryEvent(Base):
    """
    TelemetryEvent model for raw ingested telemetry data.

    This is a TimescaleDB hypertable partitioned by timestamp with 1-day chunks.
    Has 7-day retention policy (NFR-008).

    Attributes:
        event_id: UUID event identifier (part of composite PK)
        service_id: Foreign key to services table
        event_type: Type of event (log/trace/metric)
        timestamp: Event timestamp (part of composite PK for hypertable)
        severity: Event severity level
        message: Event message text
        trace_id: Distributed trace ID (optional)
        span_id: Trace span ID (optional)
        attributes: JSONB attributes
        raw_blob_s3_key: S3/MinIO key for oversized payloads
    """
    __tablename__ = "telemetry_events"

    # Composite primary key for hypertable partitioning
    event_id: PyUUID = Column(
        UUID,
        primary_key=True,
        nullable=False,
        comment="UUID v4 event identifier"
    )

    timestamp: datetime = Column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        comment="Event timestamp (partition key)"
    )

    # Foreign keys
    service_id: PyUUID = Column(
        UUID,
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key to services table"
    )

    # Data columns
    event_type: EventTypeEnum = Column(
        Enum(EventTypeEnum, name="event_type_enum", create_type=False),
        nullable=False,
        comment="Type of event"
    )

    severity: SeverityEnum = Column(
        Enum(SeverityEnum, name="severity_enum", create_type=False),
        nullable=False,
        server_default="info",
        comment="Event severity level"
    )

    message: Optional[str] = Column(
        Text,
        nullable=True,
        comment="Event message text"
    )

    trace_id: Optional[str] = Column(
        String(64),
        nullable=True,
        comment="Distributed trace ID"
    )

    span_id: Optional[str] = Column(
        String(32),
        nullable=True,
        comment="Trace span ID"
    )

    attributes: dict = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Event attributes"
    )

    raw_blob_s3_key: Optional[str] = Column(
        String(512),
        nullable=True,
        comment="S3/MinIO key for oversized payloads"
    )

    # Indexes
    __table_args__ = (
        Index("idx_telemetry_service_time", "service_id", text("timestamp DESC")),
        Index("idx_telemetry_trace_id", "trace_id", postgresql_where=text("trace_id IS NOT NULL")),
        Index("idx_telemetry_event_type_time", "event_type", text("timestamp DESC")),
    )

    # Relationships
    service = relationship("Service", back_populates="telemetry_events")

    def __repr__(self) -> str:
        return f"<TelemetryEvent(id={self.event_id}, type={self.event_type}, timestamp={self.timestamp})>"
