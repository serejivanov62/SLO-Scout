"""
Contract test for Services API endpoints
Per services-api.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import UUID, uuid4
from datetime import datetime


@pytest.mark.asyncio
async def test_create_service_returns_201_with_service(async_client: AsyncClient):
    """POST /api/v1/services should return 201 with created service"""
    request_body = {
        "name": "payment-gateway",
        "environment": "prod",
        "owner_team": "payments-team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus.monitoring.svc:9090",
            "loki": "http://loki.monitoring.svc:3100"
        },
        "label_mappings": {
            "prometheus": {
                "job": "payment-gateway",
                "namespace": "prod"
            },
            "loki": {
                "app": "payment-gateway",
                "environment": "prod"
            }
        }
    }

    response = await async_client.post("/api/v1/services", json=request_body)

    # Per services-api.yaml: 201 Created
    assert response.status_code == 201

    data = response.json()

    # Validate Service schema
    assert "id" in data
    UUID(data["id"])  # Raises ValueError if invalid UUID

    assert data["name"] == "payment-gateway"
    assert data["environment"] == "prod"
    assert data["owner_team"] == "payments-team"

    # Validate telemetry_endpoints
    assert "telemetry_endpoints" in data
    assert data["telemetry_endpoints"]["prometheus"] == "http://prometheus.monitoring.svc:9090"
    assert data["telemetry_endpoints"]["loki"] == "http://loki.monitoring.svc:3100"

    # Validate label_mappings
    assert "label_mappings" in data
    assert data["label_mappings"]["prometheus"]["job"] == "payment-gateway"
    assert data["label_mappings"]["loki"]["app"] == "payment-gateway"

    # Validate timestamps
    assert "created_at" in data
    datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))

    assert "updated_at" in data
    datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))

    # Validate status
    assert data["status"] in ["active", "inactive", "archived"]


@pytest.mark.asyncio
async def test_create_service_validates_required_fields(async_client: AsyncClient):
    """POST /api/v1/services should return 400 if required fields missing"""
    request_body = {
        "name": "payment-gateway",
        "environment": "prod"
        # Missing owner_team, telemetry_endpoints, label_mappings
    }

    response = await async_client.post("/api/v1/services", json=request_body)

    # Per services-api.yaml: 400 Bad Request
    assert response.status_code == 400

    data = response.json()
    assert "error" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_create_service_validates_environment_enum(async_client: AsyncClient):
    """POST /api/v1/services should validate environment enum"""
    request_body = {
        "name": "payment-gateway",
        "environment": "production",  # Invalid, should be "prod", "staging", or "dev"
        "owner_team": "payments-team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090"
        },
        "label_mappings": {
            "prometheus": {"job": "payment-gateway"}
        }
    }

    response = await async_client.post("/api/v1/services", json=request_body)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_service_validates_name_length(async_client: AsyncClient):
    """POST /api/v1/services should validate name length (1-255 chars)"""
    request_body = {
        "name": "",  # Too short (minLength: 1)
        "environment": "prod",
        "owner_team": "payments-team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090"
        },
        "label_mappings": {
            "prometheus": {"job": "payment-gateway"}
        }
    }

    response = await async_client.post("/api/v1/services", json=request_body)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_service_duplicate_returns_409(async_client: AsyncClient):
    """POST /api/v1/services should return 409 if service exists in same environment"""
    request_body = {
        "name": "payment-gateway",
        "environment": "prod",
        "owner_team": "payments-team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090"
        },
        "label_mappings": {
            "prometheus": {"job": "payment-gateway"}
        }
    }

    # Create first service
    response1 = await async_client.post("/api/v1/services", json=request_body)
    assert response1.status_code == 201

    # Try to create duplicate
    response2 = await async_client.post("/api/v1/services", json=request_body)

    # Per services-api.yaml: 409 Conflict
    assert response2.status_code == 409

    data = response2.json()
    assert "error" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_list_services_returns_200_with_pagination(async_client: AsyncClient):
    """GET /api/v1/services should return 200 with paginated services"""
    # Create test services first
    for i in range(3):
        await async_client.post("/api/v1/services", json={
            "name": f"service-{i}",
            "environment": "prod",
            "owner_team": "team-a",
            "telemetry_endpoints": {
                "prometheus": "http://prometheus:9090"
            },
            "label_mappings": {
                "prometheus": {"job": f"service-{i}"}
            }
        })

    response = await async_client.get("/api/v1/services")

    # Per services-api.yaml: 200 OK
    assert response.status_code == 200

    data = response.json()

    # Validate response schema
    assert "services" in data
    assert isinstance(data["services"], list)

    assert "total" in data
    assert isinstance(data["total"], int)
    assert data["total"] >= 3

    assert "limit" in data
    assert isinstance(data["limit"], int)

    assert "offset" in data
    assert isinstance(data["offset"], int)


@pytest.mark.asyncio
async def test_list_services_filters_by_environment(async_client: AsyncClient):
    """GET /api/v1/services?environment=prod should filter by environment"""
    # Create services in different environments
    await async_client.post("/api/v1/services", json={
        "name": "prod-service",
        "environment": "prod",
        "owner_team": "team-a",
        "telemetry_endpoints": {"prometheus": "http://prometheus:9090"},
        "label_mappings": {"prometheus": {"job": "prod-service"}}
    })

    await async_client.post("/api/v1/services", json={
        "name": "staging-service",
        "environment": "staging",
        "owner_team": "team-a",
        "telemetry_endpoints": {"prometheus": "http://prometheus:9090"},
        "label_mappings": {"prometheus": {"job": "staging-service"}}
    })

    response = await async_client.get("/api/v1/services?environment=prod")

    assert response.status_code == 200

    data = response.json()
    # All returned services should be in prod environment
    for service in data["services"]:
        assert service["environment"] == "prod"


@pytest.mark.asyncio
async def test_list_services_filters_by_status(async_client: AsyncClient):
    """GET /api/v1/services?status=active should filter by status"""
    response = await async_client.get("/api/v1/services?status=active")

    assert response.status_code == 200

    data = response.json()
    # All returned services should have active status
    for service in data["services"]:
        assert service["status"] == "active"


@pytest.mark.asyncio
async def test_list_services_validates_limit_range(async_client: AsyncClient):
    """GET /api/v1/services?limit=200 should return 400 (max is 100)"""
    response = await async_client.get("/api/v1/services?limit=200")

    # Per services-api.yaml: limit max is 100
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_services_pagination_works(async_client: AsyncClient):
    """GET /api/v1/services with limit and offset should paginate correctly"""
    response = await async_client.get("/api/v1/services?limit=10&offset=0")

    assert response.status_code == 200

    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert len(data["services"]) <= 10


@pytest.mark.asyncio
async def test_get_service_returns_200_with_service(async_client: AsyncClient):
    """GET /api/v1/services/{service_id} should return 200 with service details"""
    # Create a service first
    create_response = await async_client.post("/api/v1/services", json={
        "name": "test-service",
        "environment": "prod",
        "owner_team": "test-team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090"
        },
        "label_mappings": {
            "prometheus": {"job": "test-service"}
        }
    })

    assert create_response.status_code == 201
    service_id = create_response.json()["id"]

    # Get the service
    response = await async_client.get(f"/api/v1/services/{service_id}")

    # Per services-api.yaml: 200 OK
    assert response.status_code == 200

    data = response.json()

    # Validate Service schema
    assert data["id"] == service_id
    assert data["name"] == "test-service"
    assert data["environment"] == "prod"
    assert data["owner_team"] == "test-team"
    assert "telemetry_endpoints" in data
    assert "label_mappings" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert data["status"] in ["active", "inactive", "archived"]


@pytest.mark.asyncio
async def test_get_service_returns_404_for_nonexistent(async_client: AsyncClient):
    """GET /api/v1/services/{service_id} should return 404 if service not found"""
    fake_id = str(uuid4())

    response = await async_client.get(f"/api/v1/services/{fake_id}")

    # Per services-api.yaml: 404 Not Found
    assert response.status_code == 404

    data = response.json()
    assert "error" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_delete_service_returns_204(async_client: AsyncClient):
    """DELETE /api/v1/services/{service_id} should return 204 on success"""
    # Create a service first
    create_response = await async_client.post("/api/v1/services", json={
        "name": "service-to-delete",
        "environment": "prod",
        "owner_team": "test-team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090"
        },
        "label_mappings": {
            "prometheus": {"job": "service-to-delete"}
        }
    })

    assert create_response.status_code == 201
    service_id = create_response.json()["id"]

    # Delete the service
    response = await async_client.delete(f"/api/v1/services/{service_id}")

    # Per services-api.yaml: 204 No Content
    assert response.status_code == 204

    # Verify service is deleted/archived
    get_response = await async_client.get(f"/api/v1/services/{service_id}")
    assert get_response.status_code in [404, 200]  # Either not found or archived


@pytest.mark.asyncio
async def test_delete_service_with_hard_delete_flag(async_client: AsyncClient):
    """DELETE /api/v1/services/{service_id}?hard_delete=true should permanently delete"""
    # Create a service first
    create_response = await async_client.post("/api/v1/services", json={
        "name": "service-hard-delete",
        "environment": "prod",
        "owner_team": "test-team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090"
        },
        "label_mappings": {
            "prometheus": {"job": "service-hard-delete"}
        }
    })

    assert create_response.status_code == 201
    service_id = create_response.json()["id"]

    # Hard delete the service
    response = await async_client.delete(f"/api/v1/services/{service_id}?hard_delete=true")

    # Per services-api.yaml: 204 No Content
    assert response.status_code == 204

    # Verify service is permanently deleted
    get_response = await async_client.get(f"/api/v1/services/{service_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_service_returns_404_for_nonexistent(async_client: AsyncClient):
    """DELETE /api/v1/services/{service_id} should return 404 if service not found"""
    fake_id = str(uuid4())

    response = await async_client.delete(f"/api/v1/services/{fake_id}")

    # Per services-api.yaml: 404 Not Found
    assert response.status_code == 404

    data = response.json()
    assert "error" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_create_service_validates_telemetry_endpoints_min_properties(async_client: AsyncClient):
    """POST /api/v1/services should validate telemetry_endpoints has at least 1 property"""
    request_body = {
        "name": "test-service",
        "environment": "prod",
        "owner_team": "test-team",
        "telemetry_endpoints": {},  # Empty object (minProperties: 1)
        "label_mappings": {
            "prometheus": {"job": "test-service"}
        }
    }

    response = await async_client.post("/api/v1/services", json=request_body)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_service_validates_label_mappings_min_properties(async_client: AsyncClient):
    """POST /api/v1/services should validate label_mappings has at least 1 property"""
    request_body = {
        "name": "test-service",
        "environment": "prod",
        "owner_team": "test-team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090"
        },
        "label_mappings": {}  # Empty object (minProperties: 1)
    }

    response = await async_client.post("/api/v1/services", json=request_body)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_service_accepts_additional_telemetry_endpoints(async_client: AsyncClient):
    """POST /api/v1/services should accept additional telemetry endpoints beyond spec"""
    request_body = {
        "name": "multi-endpoint-service",
        "environment": "prod",
        "owner_team": "test-team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090",
            "loki": "http://loki:3100",
            "jaeger": "http://jaeger:16686",
            "custom_endpoint": "http://custom:8080"  # Additional property
        },
        "label_mappings": {
            "prometheus": {"job": "multi-endpoint-service"}
        }
    }

    response = await async_client.post("/api/v1/services", json=request_body)

    # Per services-api.yaml: additionalProperties allowed
    assert response.status_code == 201

    data = response.json()
    assert data["telemetry_endpoints"]["custom_endpoint"] == "http://custom:8080"
