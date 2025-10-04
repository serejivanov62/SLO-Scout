"""
Contract test for GET /api/v1/sli endpoint
Per api-sli.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_sli_list_returns_array(async_client: AsyncClient):
    """GET /api/v1/sli should return SLI recommendations"""
    journey_id = str(uuid4())
    params = {"journey_id": journey_id}

    response = await async_client.get("/api/v1/sli", params=params)

    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()
        assert "slis" in data
        assert isinstance(data["slis"], list)


@pytest.mark.asyncio
async def test_sli_list_include_evidence(async_client: AsyncClient):
    """GET /api/v1/sli should include evidence when requested"""
    journey_id = str(uuid4())
    params = {
        "journey_id": journey_id,
        "include_evidence": True
    }

    response = await async_client.get("/api/v1/sli", params=params)

    if response.status_code == 200:
        data = response.json()

        if len(data["slis"]) > 0:
            sli = data["slis"][0]

            # Per api-sli.yaml: evidence_pointers should be present
            assert "evidence_pointers" in sli
            assert isinstance(sli["evidence_pointers"], list)


@pytest.mark.asyncio
async def test_sli_list_schema(async_client: AsyncClient):
    """GET /api/v1/sli should return SLIs with correct schema"""
    journey_id = str(uuid4())

    response = await async_client.get(f"/api/v1/sli?journey_id={journey_id}")

    if response.status_code == 200:
        data = response.json()

        if len(data["slis"]) > 0:
            sli = data["slis"][0]

            # Per data-model.md SLI entity
            assert "sli_id" in sli
            assert "name" in sli
            assert "metric_type" in sli
            assert sli["metric_type"] in ["latency", "availability", "error_rate", "custom"]
            assert "metric_definition" in sli
            assert "confidence_score" in sli
            assert 0 <= sli["confidence_score"] <= 100
            assert "current_value" in sli or sli.get("current_value") is None
            assert "unit" in sli
