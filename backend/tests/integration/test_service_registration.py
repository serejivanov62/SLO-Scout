"""
Integration test for service registration (Step 3 of quickstart.md)

Tests the complete service registration workflow:
1. POST /api/v1/services to create service
2. Verify service persisted in database
3. Verify collector reconfiguration triggered
4. Verify reconfiguration completes within 60s (FR-006)
5. Test telemetry endpoint connectivity validation

Per spec.md FR-006: Collector reconfiguration must complete within 60 seconds

EXPECTED TO FAIL: This test will fail until the following are implemented:
- Database persistence for services
- Collector reconfiguration trigger
- Telemetry endpoint validation
"""
import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any


@pytest.mark.asyncio
async def test_service_registration_happy_path(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test successful service registration with all validations

    Steps:
    1. POST /api/v1/services with valid payload
    2. Verify 201 response with service_id
    3. Verify service persisted in database
    4. Verify collector reconfiguration triggered
    5. Verify reconfiguration completes within 60s
    """
    # Arrange: Prepare service registration payload
    service_payload = {
        "name": "checkout-api",
        "environment": "prod",
        "owner_team": "checkout-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus.prod.svc:9090",
            "otlp_endpoint": "grpc://otel-collector.prod.svc:4317",
            "loki_url": "http://loki.prod.svc:3100"
        }
    }

    # Act: Register service
    response = await async_client.post("/api/v1/services", json=service_payload)

    # Assert: HTTP 201 response
    assert response.status_code == 201, (
        f"Expected 201 Created, got {response.status_code}. "
        f"Response: {response.text}"
    )

    service_response = response.json()

    # Assert: Response structure
    assert "service_id" in service_response
    assert "name" in service_response
    assert "environment" in service_response
    assert "owner_team" in service_response
    assert "telemetry_endpoints" in service_response
    assert "status" in service_response
    assert "created_at" in service_response
    assert "updated_at" in service_response

    # Validate service_id is valid UUID
    service_id = UUID(service_response["service_id"])

    # Validate response data matches request
    assert service_response["name"] == service_payload["name"]
    assert service_response["environment"] == service_payload["environment"]
    assert service_response["owner_team"] == service_payload["owner_team"]
    assert service_response["telemetry_endpoints"] == service_payload["telemetry_endpoints"]
    assert service_response["status"] == "active"

    # Assert: Verify persistence in database
    from src.models.service import Service

    db_service = test_db.query(Service).filter(
        Service.service_id == service_id
    ).first()

    assert db_service is not None, (
        f"Service {service_id} not found in database. "
        "Database persistence not implemented."
    )

    assert db_service.name == service_payload["name"]
    assert db_service.environment.value == service_payload["environment"]
    assert db_service.owner_team == service_payload["owner_team"]
    assert db_service.telemetry_endpoints == service_payload["telemetry_endpoints"]
    assert db_service.status.value == "active"

    # Assert: Timestamps are reasonable
    assert db_service.created_at is not None
    assert db_service.updated_at is not None
    assert db_service.created_at <= datetime.utcnow()
    assert db_service.updated_at <= datetime.utcnow()


@pytest.mark.asyncio
async def test_service_registration_collector_reconfiguration(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test collector reconfiguration trigger and completion

    Per FR-006: Reconfiguration must complete within 60 seconds

    This test verifies:
    1. Collector reconfiguration is triggered
    2. Reconfiguration completes within 60s
    3. Telemetry endpoints become accessible
    """
    service_payload = {
        "name": "payments-api",
        "environment": "prod",
        "owner_team": "payments-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus.prod.svc:9090",
            "otlp_endpoint": "grpc://otel-collector.prod.svc:4317"
        }
    }

    # Mock collector reconfiguration service
    with patch('src.services.collector_manager.CollectorManager') as mock_collector:
        mock_instance = AsyncMock()
        mock_instance.reconfigure = AsyncMock(return_value={
            "status": "success",
            "reconfigured_at": datetime.utcnow().isoformat(),
            "duration_seconds": 15.5
        })
        mock_collector.return_value = mock_instance

        # Record start time for FR-006 compliance
        start_time = datetime.utcnow()

        # Act: Register service
        response = await async_client.post("/api/v1/services", json=service_payload)

        # Assert: Service created
        assert response.status_code == 201
        service_response = response.json()
        service_id = service_response["service_id"]

        # Assert: Collector reconfiguration triggered
        # This will fail until collector integration is implemented
        mock_instance.reconfigure.assert_called_once()

        # Verify reconfiguration was called with correct service data
        call_args = mock_instance.reconfigure.call_args
        assert call_args is not None
        reconfigure_payload = call_args[0][0] if call_args[0] else call_args[1]
        assert reconfigure_payload["service_id"] == service_id

        # Assert: FR-006 - Reconfiguration completes within 60 seconds
        end_time = datetime.utcnow()
        reconfiguration_duration = (end_time - start_time).total_seconds()

        assert reconfiguration_duration < 60.0, (
            f"FR-006 VIOLATION: Reconfiguration took {reconfiguration_duration:.2f}s, "
            f"must complete within 60s"
        )


@pytest.mark.asyncio
async def test_service_registration_telemetry_validation(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test telemetry endpoint connectivity validation

    This test verifies:
    1. Prometheus endpoint is reachable
    2. OTLP endpoint is reachable
    3. Invalid endpoints are rejected
    """
    # Test Case 1: Valid endpoints
    valid_payload = {
        "name": "inventory-api",
        "environment": "prod",
        "owner_team": "inventory-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus.prod.svc:9090",
            "otlp_endpoint": "grpc://otel-collector.prod.svc:4317"
        }
    }

    # Mock telemetry endpoint validator
    with patch('src.validators.telemetry_validator.TelemetryValidator') as mock_validator:
        mock_instance = MagicMock()
        mock_instance.validate_prometheus_endpoint = AsyncMock(return_value={
            "reachable": True,
            "response_time_ms": 45
        })
        mock_instance.validate_otlp_endpoint = AsyncMock(return_value={
            "reachable": True,
            "response_time_ms": 32
        })
        mock_validator.return_value = mock_instance

        # Act: Register service with valid endpoints
        response = await async_client.post("/api/v1/services", json=valid_payload)

        # Assert: Service created successfully
        assert response.status_code == 201

        # Assert: Telemetry validation was performed
        # This will fail until telemetry validation is implemented
        mock_instance.validate_prometheus_endpoint.assert_called_once_with(
            valid_payload["telemetry_endpoints"]["prometheus_url"]
        )
        mock_instance.validate_otlp_endpoint.assert_called_once_with(
            valid_payload["telemetry_endpoints"]["otlp_endpoint"]
        )


@pytest.mark.asyncio
async def test_service_registration_invalid_telemetry_endpoints(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test rejection of invalid or unreachable telemetry endpoints

    Expected behavior:
    - Return 400 Bad Request
    - Include error details about unreachable endpoint
    """
    invalid_payload = {
        "name": "test-api",
        "environment": "prod",
        "owner_team": "test-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://invalid-prometheus.local:9090",
            "otlp_endpoint": "grpc://unreachable-otel:4317"
        }
    }

    # Mock telemetry endpoint validator to simulate unreachable endpoints
    with patch('src.validators.telemetry_validator.TelemetryValidator') as mock_validator:
        mock_instance = MagicMock()
        mock_instance.validate_prometheus_endpoint = AsyncMock(return_value={
            "reachable": False,
            "error": "Connection timeout"
        })
        mock_validator.return_value = mock_instance

        # Act: Attempt to register service with invalid endpoints
        response = await async_client.post("/api/v1/services", json=invalid_payload)

        # Assert: Request rejected with 400 Bad Request
        assert response.status_code == 400, (
            "Expected 400 Bad Request for unreachable telemetry endpoints. "
            "Telemetry validation not implemented."
        )

        error_response = response.json()
        assert "detail" in error_response
        assert "telemetry" in error_response["detail"].lower() or \
               "unreachable" in error_response["detail"].lower()


@pytest.mark.asyncio
async def test_service_registration_duplicate_name_environment(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test duplicate service registration (same name + environment)

    Expected behavior:
    - First registration succeeds
    - Second registration with same name+environment returns 409 Conflict
    """
    service_payload = {
        "name": "duplicate-api",
        "environment": "prod",
        "owner_team": "test-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus.prod.svc:9090"
        }
    }

    # Act: Register service first time
    response1 = await async_client.post("/api/v1/services", json=service_payload)
    assert response1.status_code == 201

    # Act: Attempt to register duplicate service
    response2 = await async_client.post("/api/v1/services", json=service_payload)

    # Assert: Duplicate rejected with 409 Conflict
    assert response2.status_code == 409, (
        "Expected 409 Conflict for duplicate service (name+environment). "
        "Duplicate detection not implemented."
    )

    error_response = response2.json()
    assert "detail" in error_response
    assert "duplicate" in error_response["detail"].lower() or \
           "already exists" in error_response["detail"].lower()


@pytest.mark.asyncio
async def test_service_registration_different_environments_allowed(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test same service name in different environments is allowed

    Expected behavior:
    - Same name in 'prod' succeeds
    - Same name in 'staging' succeeds
    - Both services exist independently
    """
    prod_payload = {
        "name": "multi-env-api",
        "environment": "prod",
        "owner_team": "test-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus.prod.svc:9090"
        }
    }

    staging_payload = {
        "name": "multi-env-api",
        "environment": "staging",
        "owner_team": "test-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus.staging.svc:9090"
        }
    }

    # Act: Register service in prod
    response1 = await async_client.post("/api/v1/services", json=prod_payload)
    assert response1.status_code == 201
    prod_service = response1.json()

    # Act: Register same service name in staging
    response2 = await async_client.post("/api/v1/services", json=staging_payload)
    assert response2.status_code == 201
    staging_service = response2.json()

    # Assert: Both services created with different IDs
    assert prod_service["service_id"] != staging_service["service_id"]
    assert prod_service["name"] == staging_service["name"]
    assert prod_service["environment"] == "prod"
    assert staging_service["environment"] == "staging"


@pytest.mark.asyncio
async def test_service_registration_missing_required_fields(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test validation of required fields

    Expected behavior:
    - Missing 'name' returns 422 Unprocessable Entity
    - Missing 'environment' returns 422
    - Missing 'owner_team' returns 422
    - Missing 'telemetry_endpoints' returns 422
    """
    # Test missing 'name'
    payload_no_name = {
        "environment": "prod",
        "owner_team": "test-squad",
        "telemetry_endpoints": {"prometheus_url": "http://prometheus:9090"}
    }
    response = await async_client.post("/api/v1/services", json=payload_no_name)
    assert response.status_code == 422

    # Test missing 'environment'
    payload_no_env = {
        "name": "test-api",
        "owner_team": "test-squad",
        "telemetry_endpoints": {"prometheus_url": "http://prometheus:9090"}
    }
    response = await async_client.post("/api/v1/services", json=payload_no_env)
    assert response.status_code == 422

    # Test missing 'owner_team'
    payload_no_owner = {
        "name": "test-api",
        "environment": "prod",
        "telemetry_endpoints": {"prometheus_url": "http://prometheus:9090"}
    }
    response = await async_client.post("/api/v1/services", json=payload_no_owner)
    assert response.status_code == 422

    # Test missing 'telemetry_endpoints'
    payload_no_telemetry = {
        "name": "test-api",
        "environment": "prod",
        "owner_team": "test-squad"
    }
    response = await async_client.post("/api/v1/services", json=payload_no_telemetry)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_service_registration_invalid_environment(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test validation of environment enum

    Expected behavior:
    - Valid environments ('prod', 'staging', 'dev') succeed
    - Invalid environment returns 422
    """
    invalid_payload = {
        "name": "test-api",
        "environment": "production",  # Invalid - should be 'prod'
        "owner_team": "test-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus:9090"
        }
    }

    response = await async_client.post("/api/v1/services", json=invalid_payload)
    assert response.status_code == 422

    error_response = response.json()
    assert "detail" in error_response


@pytest.mark.asyncio
async def test_service_registration_collector_timeout(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test handling of collector reconfiguration timeout

    Per FR-006: If reconfiguration exceeds 60s, should timeout gracefully

    Expected behavior:
    - Service creation should not hang indefinitely
    - Should return appropriate error or warning
    """
    service_payload = {
        "name": "timeout-api",
        "environment": "prod",
        "owner_team": "test-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus.prod.svc:9090"
        }
    }

    # Mock collector that takes too long
    with patch('src.services.collector_manager.CollectorManager') as mock_collector:
        mock_instance = AsyncMock()

        # Simulate slow reconfiguration (exceeds 60s)
        async def slow_reconfigure(*args, **kwargs):
            await asyncio.sleep(65)  # Exceeds 60s limit
            return {"status": "timeout"}

        mock_instance.reconfigure = slow_reconfigure
        mock_collector.return_value = mock_instance

        # Act: Register service
        start_time = datetime.utcnow()

        # Should timeout before 65s completes
        try:
            response = await asyncio.wait_for(
                async_client.post("/api/v1/services", json=service_payload),
                timeout=70  # Allow time for test, but expect internal timeout at 60s
            )

            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            # Assert: Should complete within reasonable time (not hang for 65s)
            assert duration < 65, (
                f"Request took {duration:.2f}s, should timeout before 65s. "
                "Collector timeout handling not implemented."
            )

        except asyncio.TimeoutError:
            pytest.fail(
                "Request timed out completely. "
                "Collector reconfiguration should have internal timeout handling."
            )


@pytest.mark.asyncio
async def test_service_registration_list_services_after_creation(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test that newly created service appears in service list

    Workflow:
    1. Create service via POST
    2. List services via GET
    3. Verify new service is in list
    """
    service_payload = {
        "name": "list-test-api",
        "environment": "prod",
        "owner_team": "test-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus.prod.svc:9090"
        }
    }

    # Act: Create service
    create_response = await async_client.post("/api/v1/services", json=service_payload)
    assert create_response.status_code == 201
    created_service = create_response.json()
    service_id = created_service["service_id"]

    # Act: List all services
    list_response = await async_client.get("/api/v1/services")
    assert list_response.status_code == 200

    services_list = list_response.json()
    assert isinstance(services_list, list)

    # Assert: Created service is in list
    service_found = any(
        s["service_id"] == service_id
        for s in services_list
    )

    assert service_found, (
        f"Service {service_id} not found in GET /api/v1/services response. "
        "Service listing may not be reading from database."
    )


@pytest.mark.asyncio
async def test_service_registration_get_by_id_after_creation(
    async_client: AsyncClient,
    test_db: Session
):
    """
    Test retrieving service by ID after creation

    Workflow:
    1. Create service via POST
    2. Get service via GET /api/v1/services/{id}
    3. Verify service details match
    """
    service_payload = {
        "name": "get-test-api",
        "environment": "staging",
        "owner_team": "test-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus.staging.svc:9090",
            "otlp_endpoint": "grpc://otel-collector.staging.svc:4317"
        }
    }

    # Act: Create service
    create_response = await async_client.post("/api/v1/services", json=service_payload)
    assert create_response.status_code == 201
    created_service = create_response.json()
    service_id = created_service["service_id"]

    # Act: Get service by ID
    get_response = await async_client.get(f"/api/v1/services/{service_id}")
    assert get_response.status_code == 200

    retrieved_service = get_response.json()

    # Assert: Retrieved service matches created service
    assert retrieved_service["service_id"] == service_id
    assert retrieved_service["name"] == service_payload["name"]
    assert retrieved_service["environment"] == service_payload["environment"]
    assert retrieved_service["owner_team"] == service_payload["owner_team"]
    assert retrieved_service["telemetry_endpoints"] == service_payload["telemetry_endpoints"]
