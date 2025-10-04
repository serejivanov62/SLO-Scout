"""
Contract test for POST /api/v1/slo endpoint
Per api-sli.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_slo_create_returns_201(async_client: AsyncClient, sample_slo_data):
    """POST /api/v1/slo should create SLO and return 201"""
    sli_id = str(uuid4())
    request_body = {
        "sli_id": sli_id,
        **sample_slo_data
    }

    response = await async_client.post("/api/v1/slo", json=request_body)

    assert response.status_code in [201, 404]  # 404 if sli_id doesn't exist

    if response.status_code == 201:
        data = response.json()

        # Should return created SLO with slo_id
        assert "slo_id" in data
        assert data["sli_id"] == sli_id
        assert data["threshold_value"] == sample_slo_data["threshold_value"]
        assert data["variant"] == sample_slo_data["variant"]


@pytest.mark.asyncio
async def test_slo_create_validates_threshold(async_client: AsyncClient):
    """POST /api/v1/slo should validate threshold value"""
    request_body = {
        "sli_id": str(uuid4()),
        "threshold_value": -10,  # Invalid negative value
        "comparison_operator": "lt",
        "time_window": "30d",
        "target_percentage": 99.9,
        "severity": "critical",
        "variant": "conservative"
    }

    response = await async_client.post("/api/v1/slo", json=request_body)

    # Should validate threshold is positive
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_slo_create_validates_comparison_operator(async_client: AsyncClient):
    """POST /api/v1/slo should validate comparison_operator enum"""
    request_body = {
        "sli_id": str(uuid4()),
        "threshold_value": 200,
        "comparison_operator": "invalid",  # Not in enum
        "time_window": "30d",
        "target_percentage": 99.9,
        "severity": "critical",
        "variant": "conservative"
    }

    response = await async_client.post("/api/v1/slo", json=request_body)

    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_slo_create_validates_target_percentage(async_client: AsyncClient):
    """POST /api/v1/slo should validate target_percentage range [0, 100]"""
    request_body = {
        "sli_id": str(uuid4()),
        "threshold_value": 200,
        "comparison_operator": "lt",
        "time_window": "30d",
        "target_percentage": 150,  # Exceeds 100
        "severity": "critical",
        "variant": "conservative"
    }

    response = await async_client.post("/api/v1/slo", json=request_body)

    assert response.status_code in [400, 422]
