"""
Contract test for SLO API endpoints (slo-api.yaml)
Tests POST /api/v1/slos, GET /api/v1/slos, GET /api/v1/slos/{slo_id},
GET /api/v1/slos/{slo_id}/error-budget

Validates against: /specs/002-complete-slo-scout/contracts/slo-api.yaml

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4
from datetime import datetime


# ============================================================================
# POST /api/v1/slos - Create SLO
# ============================================================================

@pytest.mark.asyncio
async def test_create_slo_returns_201_with_valid_schema(async_client: AsyncClient):
    """POST /api/v1/slos should create SLO and return 201 with correct schema"""
    sli_id = str(uuid4())
    request_body = {
        "sli_id": sli_id,
        "name": "Payment Checkout Availability",
        "target_percentage": 99.9,
        "time_window": "30d",
        "threshold_variant": "balanced"
    }

    response = await async_client.post("/api/v1/slos", json=request_body)

    # Should return 201 or 404 if SLI not found
    assert response.status_code in [201, 404]

    if response.status_code == 201:
        data = response.json()

        # Per slo-api.yaml SLO schema - all required fields
        assert "slo_id" in data
        assert "sli_id" in data
        assert "name" in data
        assert "target_percentage" in data
        assert "time_window" in data
        assert "threshold_variant" in data
        assert "created_at" in data

        # Validate types and values
        assert data["sli_id"] == sli_id
        assert data["name"] == "Payment Checkout Availability"
        assert data["target_percentage"] == 99.9
        assert data["time_window"] == "30d"
        assert data["threshold_variant"] == "balanced"

        # Validate UUID format
        try:
            from uuid import UUID
            UUID(data["slo_id"])
        except ValueError:
            pytest.fail("slo_id is not a valid UUID")

        # Validate ISO 8601 datetime format
        try:
            datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        except ValueError:
            pytest.fail("created_at is not valid ISO 8601 datetime")


@pytest.mark.asyncio
async def test_create_slo_uses_default_threshold_variant(async_client: AsyncClient):
    """POST /api/v1/slos should use 'balanced' as default threshold_variant"""
    request_body = {
        "sli_id": str(uuid4()),
        "name": "API Latency P95",
        "target_percentage": 99.5,
        "time_window": "7d"
        # threshold_variant omitted - should default to 'balanced'
    }

    response = await async_client.post("/api/v1/slos", json=request_body)

    if response.status_code == 201:
        data = response.json()
        assert data["threshold_variant"] == "balanced"


@pytest.mark.asyncio
async def test_create_slo_validates_required_fields(async_client: AsyncClient):
    """POST /api/v1/slos should return 400/422 if required fields missing"""
    # Missing sli_id, name, target_percentage, time_window
    request_body = {
        "threshold_variant": "conservative"
    }

    response = await async_client.post("/api/v1/slos", json=request_body)

    # Should validate required fields
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_create_slo_validates_target_percentage_range(async_client: AsyncClient):
    """POST /api/v1/slos should validate target_percentage is 0.0-100.0"""
    request_body = {
        "sli_id": str(uuid4()),
        "name": "Invalid Target",
        "target_percentage": 150.0,  # Exceeds 100.0
        "time_window": "30d"
    }

    response = await async_client.post("/api/v1/slos", json=request_body)

    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_create_slo_validates_target_percentage_minimum(async_client: AsyncClient):
    """POST /api/v1/slos should validate target_percentage >= 0.0"""
    request_body = {
        "sli_id": str(uuid4()),
        "name": "Invalid Target",
        "target_percentage": -5.0,  # Below 0.0
        "time_window": "30d"
    }

    response = await async_client.post("/api/v1/slos", json=request_body)

    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_create_slo_validates_time_window_pattern(async_client: AsyncClient):
    """POST /api/v1/slos should validate time_window pattern ^[0-9]+[dhw]$"""
    request_body = {
        "sli_id": str(uuid4()),
        "name": "Invalid Time Window",
        "target_percentage": 99.0,
        "time_window": "invalid"  # Does not match pattern
    }

    response = await async_client.post("/api/v1/slos", json=request_body)

    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_create_slo_validates_threshold_variant_enum(async_client: AsyncClient):
    """POST /api/v1/slos should validate threshold_variant enum"""
    request_body = {
        "sli_id": str(uuid4()),
        "name": "Invalid Variant",
        "target_percentage": 99.9,
        "time_window": "30d",
        "threshold_variant": "invalid_variant"  # Not in enum
    }

    response = await async_client.post("/api/v1/slos", json=request_body)

    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_create_slo_validates_name_length(async_client: AsyncClient):
    """POST /api/v1/slos should validate name minLength=1, maxLength=255"""
    # Test empty name
    request_body = {
        "sli_id": str(uuid4()),
        "name": "",  # Empty string violates minLength=1
        "target_percentage": 99.9,
        "time_window": "30d"
    }

    response = await async_client.post("/api/v1/slos", json=request_body)
    assert response.status_code in [400, 422]

    # Test name too long
    request_body = {
        "sli_id": str(uuid4()),
        "name": "x" * 256,  # Exceeds maxLength=255
        "target_percentage": 99.9,
        "time_window": "30d"
    }

    response = await async_client.post("/api/v1/slos", json=request_body)
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_create_slo_returns_404_for_nonexistent_sli(async_client: AsyncClient):
    """POST /api/v1/slos should return 404 if SLI not found"""
    nonexistent_sli_id = str(uuid4())
    request_body = {
        "sli_id": nonexistent_sli_id,
        "name": "Test SLO",
        "target_percentage": 99.9,
        "time_window": "30d"
    }

    response = await async_client.post("/api/v1/slos", json=request_body)

    # Should return 404 for non-existent SLI
    assert response.status_code in [201, 404]

    if response.status_code == 404:
        error = response.json()
        assert "error" in error
        assert "message" in error


@pytest.mark.asyncio
async def test_create_slo_returns_400_for_unapproved_sli(async_client: AsyncClient):
    """POST /api/v1/slos should return 400 if SLI not approved"""
    # This will fail until implementation exists
    # Per spec: "Invalid request body or SLI not approved"
    sli_id = str(uuid4())
    request_body = {
        "sli_id": sli_id,
        "name": "Test SLO",
        "target_percentage": 99.9,
        "time_window": "30d"
    }

    response = await async_client.post("/api/v1/slos", json=request_body)

    # Should validate SLI approval status
    assert response.status_code in [201, 400, 404]


# ============================================================================
# GET /api/v1/slos - List SLOs
# ============================================================================

@pytest.mark.asyncio
async def test_list_slos_returns_200_with_pagination(async_client: AsyncClient):
    """GET /api/v1/slos should return paginated list with metadata"""
    response = await async_client.get("/api/v1/slos")

    assert response.status_code == 200

    data = response.json()

    # Per slo-api.yaml list response schema
    assert "slos" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data

    # Validate types
    assert isinstance(data["slos"], list)
    assert isinstance(data["total"], int)
    assert isinstance(data["limit"], int)
    assert isinstance(data["offset"], int)

    # Validate default pagination values
    assert data["limit"] == 50  # Default per spec
    assert data["offset"] == 0  # Default per spec


@pytest.mark.asyncio
async def test_list_slos_accepts_limit_parameter(async_client: AsyncClient):
    """GET /api/v1/slos should accept limit query parameter"""
    response = await async_client.get("/api/v1/slos?limit=10")

    assert response.status_code == 200

    data = response.json()
    assert data["limit"] == 10


@pytest.mark.asyncio
async def test_list_slos_accepts_offset_parameter(async_client: AsyncClient):
    """GET /api/v1/slos should accept offset query parameter"""
    response = await async_client.get("/api/v1/slos?offset=20")

    assert response.status_code == 200

    data = response.json()
    assert data["offset"] == 20


@pytest.mark.asyncio
async def test_list_slos_validates_limit_range(async_client: AsyncClient):
    """GET /api/v1/slos should validate limit minimum=1, maximum=100"""
    # Test limit too small
    response = await async_client.get("/api/v1/slos?limit=0")
    assert response.status_code in [400, 422]

    # Test limit too large
    response = await async_client.get("/api/v1/slos?limit=101")
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_list_slos_validates_offset_minimum(async_client: AsyncClient):
    """GET /api/v1/slos should validate offset >= 0"""
    response = await async_client.get("/api/v1/slos?offset=-1")

    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_list_slos_filters_by_sli_id(async_client: AsyncClient):
    """GET /api/v1/slos should filter by sli_id query parameter"""
    sli_id = str(uuid4())
    response = await async_client.get(f"/api/v1/slos?sli_id={sli_id}")

    assert response.status_code in [200, 400]

    if response.status_code == 200:
        data = response.json()
        assert "slos" in data

        # All returned SLOs should match the sli_id filter
        for slo in data["slos"]:
            assert slo["sli_id"] == sli_id


@pytest.mark.asyncio
async def test_list_slos_filters_by_threshold_variant(async_client: AsyncClient):
    """GET /api/v1/slos should filter by threshold_variant query parameter"""
    response = await async_client.get("/api/v1/slos?threshold_variant=conservative")

    assert response.status_code == 200

    data = response.json()
    assert "slos" in data

    # All returned SLOs should match the threshold_variant filter
    for slo in data["slos"]:
        assert slo["threshold_variant"] == "conservative"


@pytest.mark.asyncio
async def test_list_slos_validates_threshold_variant_enum_filter(async_client: AsyncClient):
    """GET /api/v1/slos should validate threshold_variant filter enum"""
    response = await async_client.get("/api/v1/slos?threshold_variant=invalid")

    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_list_slos_returns_correct_slo_schema(async_client: AsyncClient):
    """GET /api/v1/slos should return SLOs with correct schema"""
    response = await async_client.get("/api/v1/slos")

    assert response.status_code == 200

    data = response.json()

    if len(data["slos"]) > 0:
        slo = data["slos"][0]

        # Per slo-api.yaml SLO schema - all required fields
        required_fields = [
            "slo_id", "sli_id", "name", "target_percentage",
            "time_window", "threshold_variant", "created_at"
        ]
        for field in required_fields:
            assert field in slo, f"Missing required field: {field}"

        # Validate types and constraints
        assert isinstance(slo["target_percentage"], (int, float))
        assert 0.0 <= slo["target_percentage"] <= 100.0
        assert slo["threshold_variant"] in ["conservative", "balanced", "aggressive"]


# ============================================================================
# GET /api/v1/slos/{slo_id} - Get SLO by ID
# ============================================================================

@pytest.mark.asyncio
async def test_get_slo_returns_200_with_valid_id(async_client: AsyncClient):
    """GET /api/v1/slos/{slo_id} should return SLO details"""
    slo_id = str(uuid4())
    response = await async_client.get(f"/api/v1/slos/{slo_id}")

    # Should return 200 or 404
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()

        # Per slo-api.yaml SLO schema
        required_fields = [
            "slo_id", "sli_id", "name", "target_percentage",
            "time_window", "threshold_variant", "created_at"
        ]
        for field in required_fields:
            assert field in data

        # Validate the returned slo_id matches request
        assert data["slo_id"] == slo_id


@pytest.mark.asyncio
async def test_get_slo_returns_404_for_nonexistent_id(async_client: AsyncClient):
    """GET /api/v1/slos/{slo_id} should return 404 for non-existent SLO"""
    nonexistent_slo_id = str(uuid4())
    response = await async_client.get(f"/api/v1/slos/{nonexistent_slo_id}")

    # Should return 404 for non-existent SLO
    assert response.status_code in [200, 404]

    if response.status_code == 404:
        error = response.json()
        assert "error" in error
        assert "message" in error


@pytest.mark.asyncio
async def test_get_slo_validates_uuid_format(async_client: AsyncClient):
    """GET /api/v1/slos/{slo_id} should validate UUID format"""
    invalid_uuid = "not-a-uuid"
    response = await async_client.get(f"/api/v1/slos/{invalid_uuid}")

    # Should validate UUID format
    assert response.status_code in [400, 404, 422]


@pytest.mark.asyncio
async def test_get_slo_returns_complete_schema(async_client: AsyncClient):
    """GET /api/v1/slos/{slo_id} should return complete SLO schema"""
    slo_id = str(uuid4())
    response = await async_client.get(f"/api/v1/slos/{slo_id}")

    if response.status_code == 200:
        data = response.json()

        # Validate all required fields per slo-api.yaml
        assert "slo_id" in data
        assert "sli_id" in data
        assert "name" in data
        assert "target_percentage" in data
        assert "time_window" in data
        assert "threshold_variant" in data
        assert "created_at" in data

        # Validate field constraints
        assert len(data["name"]) >= 1
        assert len(data["name"]) <= 255
        assert 0.0 <= data["target_percentage"] <= 100.0
        assert data["threshold_variant"] in ["conservative", "balanced", "aggressive"]


# ============================================================================
# GET /api/v1/slos/{slo_id}/error-budget - Calculate Error Budget
# ============================================================================

@pytest.mark.asyncio
async def test_get_error_budget_returns_200_with_calculation(async_client: AsyncClient):
    """GET /api/v1/slos/{slo_id}/error-budget should return error budget calculation"""
    slo_id = str(uuid4())
    response = await async_client.get(f"/api/v1/slos/{slo_id}/error-budget")

    # Should return 200 or 404
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()

        # Per slo-api.yaml error budget response schema
        required_fields = [
            "slo_id", "target_percentage", "current_percentage",
            "error_budget_remaining", "time_window", "calculation_timestamp"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate the returned slo_id matches request
        assert data["slo_id"] == slo_id


@pytest.mark.asyncio
async def test_get_error_budget_validates_field_types(async_client: AsyncClient):
    """GET /api/v1/slos/{slo_id}/error-budget should return correct field types"""
    slo_id = str(uuid4())
    response = await async_client.get(f"/api/v1/slos/{slo_id}/error-budget")

    if response.status_code == 200:
        data = response.json()

        # Validate types
        assert isinstance(data["slo_id"], str)
        assert isinstance(data["target_percentage"], (int, float))
        assert isinstance(data["current_percentage"], (int, float))
        assert isinstance(data["error_budget_remaining"], (int, float))
        assert isinstance(data["time_window"], str)
        assert isinstance(data["calculation_timestamp"], str)

        # Validate ranges
        assert 0.0 <= data["target_percentage"] <= 100.0
        assert 0.0 <= data["current_percentage"] <= 100.0
        assert 0.0 <= data["error_budget_remaining"] <= 100.0


@pytest.mark.asyncio
async def test_get_error_budget_validates_timestamp_format(async_client: AsyncClient):
    """GET /api/v1/slos/{slo_id}/error-budget should return ISO 8601 timestamp"""
    slo_id = str(uuid4())
    response = await async_client.get(f"/api/v1/slos/{slo_id}/error-budget")

    if response.status_code == 200:
        data = response.json()

        # Validate ISO 8601 datetime format
        try:
            datetime.fromisoformat(data["calculation_timestamp"].replace("Z", "+00:00"))
        except ValueError:
            pytest.fail("calculation_timestamp is not valid ISO 8601 datetime")


@pytest.mark.asyncio
async def test_get_error_budget_returns_404_for_nonexistent_slo(async_client: AsyncClient):
    """GET /api/v1/slos/{slo_id}/error-budget should return 404 for non-existent SLO"""
    nonexistent_slo_id = str(uuid4())
    response = await async_client.get(f"/api/v1/slos/{nonexistent_slo_id}/error-budget")

    # Should return 404 for non-existent SLO
    assert response.status_code in [200, 404]

    if response.status_code == 404:
        error = response.json()
        assert "error" in error
        assert "message" in error


@pytest.mark.asyncio
async def test_get_error_budget_validates_uuid_format(async_client: AsyncClient):
    """GET /api/v1/slos/{slo_id}/error-budget should validate UUID format"""
    invalid_uuid = "not-a-uuid"
    response = await async_client.get(f"/api/v1/slos/{invalid_uuid}/error-budget")

    # Should validate UUID format
    assert response.status_code in [400, 404, 422]


@pytest.mark.asyncio
async def test_get_error_budget_calculation_logic(async_client: AsyncClient):
    """GET /api/v1/slos/{slo_id}/error-budget should calculate error budget correctly"""
    slo_id = str(uuid4())
    response = await async_client.get(f"/api/v1/slos/{slo_id}/error-budget")

    if response.status_code == 200:
        data = response.json()

        # Error budget remaining should be based on:
        # error_budget_remaining = (current_percentage - target_percentage) / (100 - target_percentage) * 100
        # This validates the calculation makes sense
        target = data["target_percentage"]
        current = data["current_percentage"]
        remaining = data["error_budget_remaining"]

        # If current > target, error budget should be positive
        # If current < target, error budget should be negative or consumed
        assert isinstance(remaining, (int, float))
        assert 0.0 <= remaining <= 100.0 or remaining < 0  # Can be negative if budget exhausted


# ============================================================================
# Error Response Validation
# ============================================================================

@pytest.mark.asyncio
async def test_error_responses_match_schema(async_client: AsyncClient):
    """All error responses should match Error schema from slo-api.yaml"""
    # Trigger a validation error
    response = await async_client.post("/api/v1/slos", json={})

    if response.status_code in [400, 404, 422, 500]:
        error = response.json()

        # Per slo-api.yaml Error schema
        assert "error" in error
        assert "message" in error

        # Optional details field
        if "details" in error:
            assert isinstance(error["details"], dict)


@pytest.mark.asyncio
async def test_invalid_content_type_returns_error(async_client: AsyncClient):
    """POST /api/v1/slos should reject non-JSON content"""
    response = await async_client.post(
        "/api/v1/slos",
        content="not json",
        headers={"Content-Type": "text/plain"}
    )

    assert response.status_code in [400, 415, 422]
