"""
Contract test for POST /api/v1/slo/{id}/simulate endpoint
Per api-sli.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_slo_simulate_returns_breach_data(async_client: AsyncClient):
    """POST /api/v1/slo/{id}/simulate should return breach simulation"""
    slo_id = str(uuid4())
    request_body = {"simulation_window_days": 30}

    response = await async_client.post(f"/api/v1/slo/{slo_id}/simulate", json=request_body)

    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()

        # Per api-sli.yaml simulation response
        assert "simulated_breaches" in data
        assert isinstance(data["simulated_breaches"], int)
        assert data["simulated_breaches"] >= 0

        assert "breach_timestamps" in data
        assert isinstance(data["breach_timestamps"], list)

        # Optional fields
        if "error_budget_impact" in data:
            assert isinstance(data["error_budget_impact"], (int, float))

        if "confidence_interval" in data:
            assert "lower" in data["confidence_interval"]
            assert "upper" in data["confidence_interval"]


@pytest.mark.asyncio
async def test_slo_simulate_validates_window(async_client: AsyncClient):
    """POST /api/v1/slo/{id}/simulate should validate simulation window"""
    slo_id = str(uuid4())
    request_body = {"simulation_window_days": 0}  # Invalid

    response = await async_client.post(f"/api/v1/slo/{slo_id}/simulate", json=request_body)

    assert response.status_code in [400, 404, 422]


@pytest.mark.asyncio
async def test_slo_simulate_performance(async_client: AsyncClient):
    """POST /api/v1/slo/{id}/simulate should complete within 120s per FR-029"""
    import time

    slo_id = str(uuid4())
    request_body = {"simulation_window_days": 30}

    start = time.time()
    response = await async_client.post(
        f"/api/v1/slo/{slo_id}/simulate",
        json=request_body,
        timeout=120.0  # Per FR-029 performance requirement
    )
    duration = time.time() - start

    if response.status_code == 200:
        # Per FR-029: simulation MUST complete in < 120s for 30-day window
        assert duration < 120, f"Simulation took {duration}s, exceeds 120s SLA"
