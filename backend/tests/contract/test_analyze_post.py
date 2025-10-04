"""
Contract test for POST /api/v1/analyze endpoint
Per api-analyze.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import UUID


@pytest.mark.asyncio
async def test_analyze_post_returns_202_with_job_id(async_client: AsyncClient):
    """POST /api/v1/analyze should return 202 with job_id and status"""
    request_body = {
        "service_name": "payments-api",
        "environment": "prod",
        "analysis_window_days": 30,
        "force_refresh": False
    }

    response = await async_client.post("/api/v1/analyze", json=request_body)

    # Per api-analyze.yaml: 202 Accepted
    assert response.status_code == 202

    data = response.json()
    # Assert job_id is valid UUID
    assert "job_id" in data
    UUID(data["job_id"])  # Raises ValueError if invalid

    # Assert status is enum [pending, running]
    assert data["status"] in ["pending", "running"]

    # Assert estimated_duration_seconds is integer
    assert isinstance(data.get("estimated_duration_seconds"), int)


@pytest.mark.asyncio
async def test_analyze_post_validates_required_fields(async_client: AsyncClient):
    """POST /api/v1/analyze should return 400 if required fields missing"""
    request_body = {
        "environment": "prod"
        # Missing service_name
    }

    response = await async_client.post("/api/v1/analyze", json=request_body)

    # Per api-analyze.yaml: 400 Bad Request
    assert response.status_code == 400

    data = response.json()
    assert "error_code" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_analyze_post_validates_environment_enum(async_client: AsyncClient):
    """POST /api/v1/analyze should validate environment enum"""
    request_body = {
        "service_name": "payments-api",
        "environment": "production"  # Invalid, should be "prod"
    }

    response = await async_client.post("/api/v1/analyze", json=request_body)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_analyze_post_validates_window_range(async_client: AsyncClient):
    """POST /api/v1/analyze should validate analysis_window_days range [1, 90]"""
    request_body = {
        "service_name": "payments-api",
        "environment": "prod",
        "analysis_window_days": 100  # Exceeds max 90
    }

    response = await async_client.post("/api/v1/analyze", json=request_body)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_analyze_post_service_not_found(async_client: AsyncClient):
    """POST /api/v1/analyze should return 404 if service not registered"""
    request_body = {
        "service_name": "nonexistent-service",
        "environment": "prod"
    }

    response = await async_client.post("/api/v1/analyze", json=request_body)

    # Per api-analyze.yaml: 404 Not Found
    assert response.status_code == 404
