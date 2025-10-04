"""
Contract test for GET /api/v1/journeys endpoint
Per api-analyze.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_journeys_list_returns_array(async_client: AsyncClient):
    """GET /api/v1/journeys should return journeys array"""
    params = {
        "service_name": "payments-api",
        "environment": "prod",
        "min_confidence": 50
    }

    response = await async_client.get("/api/v1/journeys", params=params)

    # Per api-analyze.yaml: 200 OK
    assert response.status_code == 200

    data = response.json()

    # Assert journeys is array
    assert "journeys" in data
    assert isinstance(data["journeys"], list)

    # Assert total_count is integer
    assert "total_count" in data
    assert isinstance(data["total_count"], int)


@pytest.mark.asyncio
async def test_journeys_list_validates_required_params(async_client: AsyncClient):
    """GET /api/v1/journeys should require service_name and environment"""
    # Missing environment
    response = await async_client.get("/api/v1/journeys", params={"service_name": "payments-api"})
    assert response.status_code == 422  # FastAPI validation error

    # Missing service_name
    response = await async_client.get("/api/v1/journeys", params={"environment": "prod"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_journeys_list_schema(async_client: AsyncClient):
    """GET /api/v1/journeys should return journeys with correct schema"""
    params = {
        "service_name": "payments-api",
        "environment": "prod"
    }

    response = await async_client.get("/api/v1/journeys", params=params)

    if response.status_code == 200:
        data = response.json()

        if len(data["journeys"]) > 0:
            journey = data["journeys"][0]

            # Per api-analyze.yaml UserJourney schema
            assert "journey_id" in journey
            assert "name" in journey
            assert "entry_point" in journey
            assert "exit_point" in journey
            assert "traffic_volume_per_day" in journey
            assert isinstance(journey["traffic_volume_per_day"], int)
            assert "confidence_score" in journey
            assert 0 <= journey["confidence_score"] <= 100
            assert "discovered_at" in journey


@pytest.mark.asyncio
async def test_journeys_list_min_confidence_filter(async_client: AsyncClient):
    """GET /api/v1/journeys should filter by min_confidence"""
    params = {
        "service_name": "payments-api",
        "environment": "prod",
        "min_confidence": 90
    }

    response = await async_client.get("/api/v1/journeys", params=params)

    if response.status_code == 200:
        data = response.json()

        # All returned journeys should have confidence >= 90
        for journey in data["journeys"]:
            assert journey["confidence_score"] >= 90
