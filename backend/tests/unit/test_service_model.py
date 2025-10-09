"""
Unit tests for Service model

Tests Service model constraints:
- Unique name+environment combination
- Status enum validation
- JSONB field validation
- Default values
- Nullable/non-nullable fields
"""
import pytest
from uuid import uuid4
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from src.models.service import Service, ServiceStatusEnum, EnvironmentEnum


class TestServiceModelConstraints:
    """Test Service model CHECK constraints and validations"""

    def test_service_creation_with_valid_data(self, test_db):
        """Test creating a service with all valid fields"""
        service = Service(
            name="payments-api",
            environment=EnvironmentEnum.PROD,
            owner_team="payments-squad",
            telemetry_endpoints={
                "prometheus_url": "http://prometheus:9090",
                "otlp_endpoint": "grpc://otel-collector:4317"
            },
            label_mappings={
                "prometheus": {"service": "payments-api"},
                "jaeger": {"service.name": "payments-api"}
            },
            status=ServiceStatusEnum.ACTIVE
        )
        test_db.add(service)
        test_db.commit()
        test_db.refresh(service)

        assert service.id is not None
        assert service.name == "payments-api"
        assert service.environment == EnvironmentEnum.PROD
        assert service.status == ServiceStatusEnum.ACTIVE

    def test_unique_name_environment_constraint(self, test_db):
        """Test that name+environment combination must be unique"""
        # Create first service
        service1 = Service(
            name="payments-api",
            environment=EnvironmentEnum.PROD,
            owner_team="payments-squad",
            telemetry_endpoints={"prometheus_url": "http://test"},
            label_mappings={"prometheus": {}},
            status=ServiceStatusEnum.ACTIVE
        )
        test_db.add(service1)
        test_db.commit()

        # Try to create duplicate service with same name+environment
        with pytest.raises(IntegrityError):
            service2 = Service(
                name="payments-api",
                environment=EnvironmentEnum.PROD,  # Same as service1
                owner_team="other-team",
                telemetry_endpoints={"prometheus_url": "http://test2"},
                label_mappings={"prometheus": {}},
                status=ServiceStatusEnum.ACTIVE
            )
            test_db.add(service2)
            test_db.commit()

    def test_same_name_different_environment_allowed(self, test_db):
        """Test that same name with different environment is allowed"""
        service1 = Service(
            name="payments-api",
            environment=EnvironmentEnum.PROD,
            owner_team="payments-squad",
            telemetry_endpoints={"prometheus_url": "http://test"},
            label_mappings={"prometheus": {}},
            status=ServiceStatusEnum.ACTIVE
        )
        test_db.add(service1)
        test_db.commit()

        # Same name but different environment should succeed
        service2 = Service(
            name="payments-api",
            environment=EnvironmentEnum.STAGING,  # Different environment
            owner_team="payments-squad",
            telemetry_endpoints={"prometheus_url": "http://test"},
            label_mappings={"prometheus": {}},
            status=ServiceStatusEnum.ACTIVE
        )
        test_db.add(service2)
        test_db.commit()
        test_db.refresh(service2)

        assert service2.id is not None
        assert service2.environment == EnvironmentEnum.STAGING

    def test_service_status_enum_valid_values(self, test_db):
        """Test that all valid ServiceStatus enum values work"""
        statuses = [
            ServiceStatusEnum.ACTIVE,
            ServiceStatusEnum.INACTIVE,
            ServiceStatusEnum.ARCHIVED
        ]

        for idx, status in enumerate(statuses):
            service = Service(
                name=f"service-{status.value}",
                environment=EnvironmentEnum.PROD,
                owner_team="test-team",
                telemetry_endpoints={"prometheus_url": "http://test"},
                label_mappings={"prometheus": {}},
                status=status
            )
            test_db.add(service)
            test_db.commit()
            test_db.refresh(service)

            assert service.status == status

    def test_service_status_enum_invalid_value(self, test_db):
        """Test that invalid status values are rejected"""
        with pytest.raises((ValueError, AttributeError)):
            service = Service(
                name="test-service",
                environment=EnvironmentEnum.PROD,
                owner_team="test-team",
                telemetry_endpoints={"prometheus_url": "http://test"},
                label_mappings={"prometheus": {}},
                status="invalid_status"
            )

    def test_environment_enum_valid_values(self, test_db):
        """Test that all valid Environment enum values work"""
        environments = [
            EnvironmentEnum.PROD,
            EnvironmentEnum.STAGING,
            EnvironmentEnum.DEV
        ]

        for idx, env in enumerate(environments):
            service = Service(
                name=f"service-{env.value}",
                environment=env,
                owner_team="test-team",
                telemetry_endpoints={"prometheus_url": "http://test"},
                label_mappings={"prometheus": {}},
                status=ServiceStatusEnum.ACTIVE
            )
            test_db.add(service)
            test_db.commit()
            test_db.refresh(service)

            assert service.environment == env

    def test_environment_enum_invalid_value(self, test_db):
        """Test that invalid environment values are rejected"""
        with pytest.raises((ValueError, AttributeError)):
            service = Service(
                name="test-service",
                environment="production",  # Invalid - should be "prod"
                owner_team="test-team",
                telemetry_endpoints={"prometheus_url": "http://test"},
                label_mappings={"prometheus": {}},
                status=ServiceStatusEnum.ACTIVE
            )

    def test_telemetry_endpoints_jsonb_valid(self, test_db):
        """Test that valid JSON structures are accepted for telemetry_endpoints"""
        valid_endpoints = [
            {"prometheus_url": "http://prometheus:9090"},
            {
                "prometheus_url": "http://prometheus:9090",
                "otlp_endpoint": "grpc://otel-collector:4317",
                "loki_url": "http://loki:3100",
                "jaeger_url": "http://jaeger:16686"
            },
            {},  # Empty dict is valid JSON
        ]

        for idx, endpoints in enumerate(valid_endpoints):
            service = Service(
                name=f"service-{idx}",
                environment=EnvironmentEnum.PROD,
                owner_team="test-team",
                telemetry_endpoints=endpoints,
                label_mappings={"prometheus": {}},
                status=ServiceStatusEnum.ACTIVE
            )
            test_db.add(service)
            test_db.commit()
            test_db.refresh(service)

            assert service.telemetry_endpoints == endpoints

    def test_label_mappings_jsonb_valid(self, test_db):
        """Test that valid JSON structures are accepted for label_mappings"""
        valid_mappings = [
            {"prometheus": {"service": "test"}},
            {
                "prometheus": {"service": "test", "environment": "prod"},
                "jaeger": {"service.name": "test"},
                "loki": {"app": "test"}
            },
            {},  # Empty dict is valid JSON
        ]

        for idx, mappings in enumerate(valid_mappings):
            service = Service(
                name=f"service-{idx}",
                environment=EnvironmentEnum.PROD,
                owner_team="test-team",
                telemetry_endpoints={"prometheus_url": "http://test"},
                label_mappings=mappings,
                status=ServiceStatusEnum.ACTIVE
            )
            test_db.add(service)
            test_db.commit()
            test_db.refresh(service)

            assert service.label_mappings == mappings


class TestServiceModelDefaults:
    """Test Service model default values"""

    def test_service_default_status(self, test_db):
        """Test that status defaults to ACTIVE"""
        service = Service(
            name="test-service",
            environment=EnvironmentEnum.PROD,
            owner_team="test-team",
            telemetry_endpoints={"prometheus_url": "http://test"},
            label_mappings={"prometheus": {}}
        )
        test_db.add(service)
        test_db.commit()
        test_db.refresh(service)

        assert service.status == ServiceStatusEnum.ACTIVE

    def test_service_timestamps_auto_set(self, test_db):
        """Test that created_at and updated_at are automatically set"""
        service = Service(
            name="test-service",
            environment=EnvironmentEnum.PROD,
            owner_team="test-team",
            telemetry_endpoints={"prometheus_url": "http://test"},
            label_mappings={"prometheus": {}}
        )
        test_db.add(service)
        test_db.commit()
        test_db.refresh(service)

        assert service.created_at is not None
        assert service.updated_at is not None
        assert isinstance(service.created_at, datetime)
        assert isinstance(service.updated_at, datetime)

    def test_service_id_auto_generated(self, test_db):
        """Test that service ID is auto-generated if not provided"""
        service = Service(
            name="test-service",
            environment=EnvironmentEnum.PROD,
            owner_team="test-team",
            telemetry_endpoints={"prometheus_url": "http://test"},
            label_mappings={"prometheus": {}}
        )
        test_db.add(service)
        test_db.commit()
        test_db.refresh(service)

        assert service.id is not None


class TestServiceModelNullability:
    """Test Service model nullable and non-nullable fields"""

    def test_name_not_nullable(self, test_db):
        """Test that name cannot be NULL"""
        with pytest.raises(IntegrityError):
            service = Service(
                name=None,  # Should fail
                environment=EnvironmentEnum.PROD,
                owner_team="test-team",
                telemetry_endpoints={"prometheus_url": "http://test"},
                label_mappings={"prometheus": {}}
            )
            test_db.add(service)
            test_db.commit()

    def test_environment_not_nullable(self, test_db):
        """Test that environment cannot be NULL"""
        with pytest.raises(IntegrityError):
            service = Service(
                name="test-service",
                environment=None,  # Should fail
                owner_team="test-team",
                telemetry_endpoints={"prometheus_url": "http://test"},
                label_mappings={"prometheus": {}}
            )
            test_db.add(service)
            test_db.commit()

    def test_owner_team_not_nullable(self, test_db):
        """Test that owner_team cannot be NULL"""
        with pytest.raises(IntegrityError):
            service = Service(
                name="test-service",
                environment=EnvironmentEnum.PROD,
                owner_team=None,  # Should fail
                telemetry_endpoints={"prometheus_url": "http://test"},
                label_mappings={"prometheus": {}}
            )
            test_db.add(service)
            test_db.commit()

    def test_telemetry_endpoints_not_nullable(self, test_db):
        """Test that telemetry_endpoints cannot be NULL"""
        with pytest.raises(IntegrityError):
            service = Service(
                name="test-service",
                environment=EnvironmentEnum.PROD,
                owner_team="test-team",
                telemetry_endpoints=None,  # Should fail
                label_mappings={"prometheus": {}}
            )
            test_db.add(service)
            test_db.commit()

    def test_label_mappings_not_nullable(self, test_db):
        """Test that label_mappings cannot be NULL"""
        with pytest.raises(IntegrityError):
            service = Service(
                name="test-service",
                environment=EnvironmentEnum.PROD,
                owner_team="test-team",
                telemetry_endpoints={"prometheus_url": "http://test"},
                label_mappings=None  # Should fail
            )
            test_db.add(service)
            test_db.commit()


class TestServiceModelRelationships:
    """Test Service model relationships"""

    def test_service_telemetry_events_relationship(self, test_db):
        """Test that Service has telemetry_events relationship"""
        service = Service(
            name="test-service",
            environment=EnvironmentEnum.PROD,
            owner_team="test-team",
            telemetry_endpoints={"prometheus_url": "http://test"},
            label_mappings={"prometheus": {}}
        )
        test_db.add(service)
        test_db.commit()

        # Check relationship exists
        assert hasattr(service, 'telemetry_events')
        assert service.telemetry_events == []

    def test_service_user_journeys_relationship(self, test_db):
        """Test that Service has user_journeys relationship"""
        service = Service(
            name="test-service",
            environment=EnvironmentEnum.PROD,
            owner_team="test-team",
            telemetry_endpoints={"prometheus_url": "http://test"},
            label_mappings={"prometheus": {}}
        )
        test_db.add(service)
        test_db.commit()

        # Check relationship exists
        assert hasattr(service, 'user_journeys')
        assert service.user_journeys == []

    def test_service_capsules_relationship(self, test_db):
        """Test that Service has capsules relationship"""
        service = Service(
            name="test-service",
            environment=EnvironmentEnum.PROD,
            owner_team="test-team",
            telemetry_endpoints={"prometheus_url": "http://test"},
            label_mappings={"prometheus": {}}
        )
        test_db.add(service)
        test_db.commit()

        # Check relationship exists
        assert hasattr(service, 'capsules')
        assert service.capsules == []
