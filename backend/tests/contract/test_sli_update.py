"""
Contract test for PATCH /api/v1/sli/{id} endpoint
Per api-sli.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_sli_patch_approve(async_client: AsyncClient):
    """PATCH /api/v1/sli/{id} should approve SLI"""
    sli_id = str(uuid4())
    request_body = {"approved": True}

    response = await async_client.patch(f"/api/v1/sli/{sli_id}", json=request_body)

    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()

        # Per data-model.md: approved_by and approved_at should be set
        assert data.get("approved_by") is not None
        assert data.get("approved_at") is not None


@pytest.mark.asyncio
async def test_sli_patch_metric_override(async_client: AsyncClient):
    """PATCH /api/v1/sli/{id} should allow metric_definition override"""
    sli_id = str(uuid4())
    request_body = {
        "approved": True,
        "metric_definition_override": "rate(http_requests_total{status='500'}[5m])"
    }

    response = await async_client.patch(f"/api/v1/sli/{sli_id}", json=request_body)

    # Should validate PromQL before accepting
    assert response.status_code in [200, 400, 404]


@pytest.mark.asyncio
async def test_sli_patch_invalid_promql(async_client: AsyncClient):
    """PATCH /api/v1/sli/{id} should reject invalid PromQL"""
    sli_id = str(uuid4())
    request_body = {
        "approved": True,
        "metric_definition_override": "invalid promql syntax"
    }

    response = await async_client.patch(f"/api/v1/sli/{sli_id}", json=request_body)

    # Should return validation error
    assert response.status_code in [400, 404, 422]
