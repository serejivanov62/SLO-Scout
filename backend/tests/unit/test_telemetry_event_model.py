"""
Unit tests for TelemetryEvent model

Tests TelemetryEvent model constraints:
- Hypertable composite primary key (time, event_id)
- Event type enum validation
- Severity enum validation
- Retention policy
- JSONB field validation (metadata, tags)
- Timestamp fields
- Nullable/non-nullable fields

Note: This test file is written in TDD style - the TelemetryEvent model
does not exist yet. Tests will fail until the model is implemented.
"""
import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from decimal import Decimal

# Note: Import will fail until model is created
try:
    from src.models.telemetry_event import TelemetryEvent, EventType, Severity
except ImportError:
    pytest.skip("TelemetryEvent model not yet implemented", allow_module_level=True)


class TestTelemetryEventModelConstraints:
    """Test TelemetryEvent model CHECK constraints and validations"""

    def test_telemetry_event_creation_with_valid_data(self, test_db):
        """Test creating a telemetry event with all valid fields"""
        event = TelemetryEvent(
            event_id=uuid4(),
            time=datetime.utcnow(),
            service_id=uuid4(),
            event_type=EventType.TRACE,
            severity=Severity.INFO,
            source="otel-collector",
            metadata={
                "trace_id": "abc123",
                "span_id": "def456",
                "duration_ms": 150
            },
            tags={"environment": "prod", "region": "us-west-2"}
        )
        test_db.add(event)
        test_db.commit()
        test_db.refresh(event)

        assert event.event_id is not None
        assert event.event_type == EventType.TRACE
        assert event.severity == Severity.INFO

    def test_event_type_enum_valid_values(self, test_db):
        """Test that all valid EventType enum values work"""
        event_types = [
            EventType.TRACE,
            EventType.METRIC,
            EventType.LOG,
            EventType.ALERT
        ]

        for event_type in event_types:
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow() + timedelta(seconds=1),  # Unique time
                service_id=uuid4(),
                event_type=event_type,
                severity=Severity.INFO,
                source="test-source",
                metadata={},
                tags={}
            )
            test_db.add(event)
            test_db.commit()
            test_db.refresh(event)

            assert event.event_type == event_type

    def test_event_type_enum_invalid_value(self, test_db):
        """Test that invalid event_type values are rejected"""
        with pytest.raises((ValueError, AttributeError)):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow(),
                service_id=uuid4(),
                event_type="invalid_type",
                severity=Severity.INFO,
                source="test-source",
                metadata={},
                tags={}
            )

    def test_severity_enum_valid_values(self, test_db):
        """Test that all valid Severity enum values work"""
        severities = [
            Severity.DEBUG,
            Severity.INFO,
            Severity.WARNING,
            Severity.ERROR,
            Severity.CRITICAL
        ]

        for severity in severities:
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow() + timedelta(seconds=1),  # Unique time
                service_id=uuid4(),
                event_type=EventType.LOG,
                severity=severity,
                source="test-source",
                metadata={},
                tags={}
            )
            test_db.add(event)
            test_db.commit()
            test_db.refresh(event)

            assert event.severity == severity

    def test_severity_enum_invalid_value(self, test_db):
        """Test that invalid severity values are rejected"""
        with pytest.raises((ValueError, AttributeError)):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow(),
                service_id=uuid4(),
                event_type=EventType.LOG,
                severity="invalid_severity",
                source="test-source",
                metadata={},
                tags={}
            )


class TestTelemetryEventCompositePrimaryKey:
    """Test TelemetryEvent composite primary key (time, event_id)"""

    def test_composite_pk_both_fields_required(self, test_db):
        """Test that both time and event_id are required for PK"""
        # Test missing time
        with pytest.raises(IntegrityError):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=None,  # Should fail
                service_id=uuid4(),
                event_type=EventType.TRACE,
                severity=Severity.INFO,
                source="test-source",
                metadata={},
                tags={}
            )
            test_db.add(event)
            test_db.commit()

    def test_composite_pk_uniqueness(self, test_db):
        """Test that composite PK (time, event_id) enforces uniqueness"""
        event_id = uuid4()
        timestamp = datetime.utcnow()

        # Create first event
        event1 = TelemetryEvent(
            event_id=event_id,
            time=timestamp,
            service_id=uuid4(),
            event_type=EventType.TRACE,
            severity=Severity.INFO,
            source="test-source",
            metadata={},
            tags={}
        )
        test_db.add(event1)
        test_db.commit()

        # Try to create duplicate event with same time and event_id
        with pytest.raises(IntegrityError):
            event2 = TelemetryEvent(
                event_id=event_id,
                time=timestamp,  # Same time
                service_id=uuid4(),
                event_type=EventType.LOG,
                severity=Severity.WARNING,
                source="test-source2",
                metadata={},
                tags={}
            )
            test_db.add(event2)
            test_db.commit()

    def test_same_event_id_different_time_allowed(self, test_db):
        """Test that same event_id with different time is allowed"""
        event_id = uuid4()

        event1 = TelemetryEvent(
            event_id=event_id,
            time=datetime.utcnow(),
            service_id=uuid4(),
            event_type=EventType.TRACE,
            severity=Severity.INFO,
            source="test-source",
            metadata={},
            tags={}
        )
        test_db.add(event1)
        test_db.commit()

        # Same event_id but different time should work
        event2 = TelemetryEvent(
            event_id=event_id,
            time=datetime.utcnow() + timedelta(seconds=1),
            service_id=uuid4(),
            event_type=EventType.LOG,
            severity=Severity.WARNING,
            source="test-source",
            metadata={},
            tags={}
        )
        test_db.add(event2)
        test_db.commit()
        test_db.refresh(event2)

        assert event2.event_id == event_id


class TestTelemetryEventJSONBFields:
    """Test TelemetryEvent JSONB field validation"""

    def test_metadata_jsonb_valid(self, test_db):
        """Test that valid JSON structures are accepted for metadata"""
        valid_metadata = [
            {"trace_id": "abc123"},
            {
                "trace_id": "abc123",
                "span_id": "def456",
                "duration_ms": 150,
                "http_status_code": 200
            },
            {},  # Empty dict is valid
        ]

        for idx, metadata in enumerate(valid_metadata):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow() + timedelta(seconds=idx),
                service_id=uuid4(),
                event_type=EventType.TRACE,
                severity=Severity.INFO,
                source="test-source",
                metadata=metadata,
                tags={}
            )
            test_db.add(event)
            test_db.commit()
            test_db.refresh(event)

            assert event.metadata == metadata

    def test_tags_jsonb_valid(self, test_db):
        """Test that valid JSON structures are accepted for tags"""
        valid_tags = [
            {"environment": "prod"},
            {"environment": "prod", "region": "us-west-2", "team": "payments"},
            {},  # Empty dict is valid
        ]

        for idx, tags in enumerate(valid_tags):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow() + timedelta(seconds=idx),
                service_id=uuid4(),
                event_type=EventType.METRIC,
                severity=Severity.INFO,
                source="test-source",
                metadata={},
                tags=tags
            )
            test_db.add(event)
            test_db.commit()
            test_db.refresh(event)

            assert event.tags == tags

    def test_metadata_not_nullable(self, test_db):
        """Test that metadata cannot be NULL"""
        with pytest.raises(IntegrityError):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow(),
                service_id=uuid4(),
                event_type=EventType.TRACE,
                severity=Severity.INFO,
                source="test-source",
                metadata=None,  # Should fail
                tags={}
            )
            test_db.add(event)
            test_db.commit()

    def test_tags_not_nullable(self, test_db):
        """Test that tags cannot be NULL"""
        with pytest.raises(IntegrityError):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow(),
                service_id=uuid4(),
                event_type=EventType.TRACE,
                severity=Severity.INFO,
                source="test-source",
                metadata={},
                tags=None  # Should fail
            )
            test_db.add(event)
            test_db.commit()


class TestTelemetryEventNullability:
    """Test TelemetryEvent model nullable and non-nullable fields"""

    def test_service_id_not_nullable(self, test_db):
        """Test that service_id cannot be NULL"""
        with pytest.raises(IntegrityError):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow(),
                service_id=None,  # Should fail
                event_type=EventType.TRACE,
                severity=Severity.INFO,
                source="test-source",
                metadata={},
                tags={}
            )
            test_db.add(event)
            test_db.commit()

    def test_event_type_not_nullable(self, test_db):
        """Test that event_type cannot be NULL"""
        with pytest.raises(IntegrityError):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow(),
                service_id=uuid4(),
                event_type=None,  # Should fail
                severity=Severity.INFO,
                source="test-source",
                metadata={},
                tags={}
            )
            test_db.add(event)
            test_db.commit()

    def test_severity_not_nullable(self, test_db):
        """Test that severity cannot be NULL"""
        with pytest.raises(IntegrityError):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow(),
                service_id=uuid4(),
                event_type=EventType.TRACE,
                severity=None,  # Should fail
                source="test-source",
                metadata={},
                tags={}
            )
            test_db.add(event)
            test_db.commit()

    def test_source_not_nullable(self, test_db):
        """Test that source cannot be NULL"""
        with pytest.raises(IntegrityError):
            event = TelemetryEvent(
                event_id=uuid4(),
                time=datetime.utcnow(),
                service_id=uuid4(),
                event_type=EventType.TRACE,
                severity=Severity.INFO,
                source=None,  # Should fail
                metadata={},
                tags={}
            )
            test_db.add(event)
            test_db.commit()


class TestTelemetryEventRetention:
    """Test TelemetryEvent retention policy behavior"""

    def test_old_events_can_be_deleted(self, test_db):
        """Test that old events can be deleted (simulating retention policy)"""
        # Create an old event
        old_time = datetime.utcnow() - timedelta(days=90)
        old_event = TelemetryEvent(
            event_id=uuid4(),
            time=old_time,
            service_id=uuid4(),
            event_type=EventType.LOG,
            severity=Severity.INFO,
            source="test-source",
            metadata={},
            tags={}
        )
        test_db.add(old_event)
        test_db.commit()

        event_id = old_event.event_id
        event_time = old_event.time

        # Delete the old event
        test_db.delete(old_event)
        test_db.commit()

        # Verify it's deleted
        deleted_event = test_db.query(TelemetryEvent).filter_by(
            event_id=event_id,
            time=event_time
        ).first()
        assert deleted_event is None

    def test_events_queryable_by_time_range(self, test_db):
        """Test that events can be queried by time range (for retention queries)"""
        now = datetime.utcnow()
        recent_time = now - timedelta(days=7)
        old_time = now - timedelta(days=90)

        # Create events at different times
        recent_event = TelemetryEvent(
            event_id=uuid4(),
            time=recent_time,
            service_id=uuid4(),
            event_type=EventType.TRACE,
            severity=Severity.INFO,
            source="test-source",
            metadata={},
            tags={}
        )
        old_event = TelemetryEvent(
            event_id=uuid4(),
            time=old_time,
            service_id=uuid4(),
            event_type=EventType.TRACE,
            severity=Severity.INFO,
            source="test-source",
            metadata={},
            tags={}
        )
        test_db.add(recent_event)
        test_db.add(old_event)
        test_db.commit()

        # Query for events older than 30 days
        cutoff_date = now - timedelta(days=30)
        old_events = test_db.query(TelemetryEvent).filter(
            TelemetryEvent.time < cutoff_date
        ).all()

        assert len(old_events) == 1
        assert old_events[0].event_id == old_event.event_id


class TestTelemetryEventTimestamps:
    """Test TelemetryEvent timestamp handling"""

    def test_time_field_stores_timezone_aware_datetime(self, test_db):
        """Test that time field can store timezone-aware datetime"""
        now = datetime.utcnow()
        event = TelemetryEvent(
            event_id=uuid4(),
            time=now,
            service_id=uuid4(),
            event_type=EventType.TRACE,
            severity=Severity.INFO,
            source="test-source",
            metadata={},
            tags={}
        )
        test_db.add(event)
        test_db.commit()
        test_db.refresh(event)

        assert event.time is not None
        assert isinstance(event.time, datetime)

    def test_events_ordered_by_time(self, test_db):
        """Test that events can be properly ordered by time"""
        base_time = datetime.utcnow()

        # Create events with different timestamps
        event1 = TelemetryEvent(
            event_id=uuid4(),
            time=base_time,
            service_id=uuid4(),
            event_type=EventType.TRACE,
            severity=Severity.INFO,
            source="test-source",
            metadata={},
            tags={}
        )
        event2 = TelemetryEvent(
            event_id=uuid4(),
            time=base_time + timedelta(seconds=10),
            service_id=uuid4(),
            event_type=EventType.TRACE,
            severity=Severity.INFO,
            source="test-source",
            metadata={},
            tags={}
        )
        event3 = TelemetryEvent(
            event_id=uuid4(),
            time=base_time + timedelta(seconds=5),
            service_id=uuid4(),
            event_type=EventType.TRACE,
            severity=Severity.INFO,
            source="test-source",
            metadata={},
            tags={}
        )

        test_db.add_all([event1, event2, event3])
        test_db.commit()

        # Query events ordered by time
        events = test_db.query(TelemetryEvent).order_by(
            TelemetryEvent.time.asc()
        ).all()

        assert len(events) == 3
        assert events[0].time < events[1].time < events[2].time
