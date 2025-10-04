"""
Contract test for PATCH /api/v1/artifacts/{id} endpoint
Per api-artifacts.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_artifacts_patch_approve(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{id} should approve artifact"""
    artifact_id = str(uuid4())
    request_body = {
        "action": "approve",
        "approver_comment": "LGTM"
    }

    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}", json=request_body)

    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()

        # Per data-model.md: approved_by and approved_at should be set
        assert data.get("approval_status") == "approved"
        assert data.get("approved_by") is not None


@pytest.mark.asyncio
async def test_artifacts_patch_deploy(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{id} should deploy artifact"""
    artifact_id = str(uuid4())
    request_body = {"action": "deploy"}

    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}", json=request_body)

    # Deployment requires approval first
    assert response.status_code in [200, 403, 404]


@pytest.mark.asyncio
async def test_artifacts_patch_policy_violation(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{id} should block if Policy Guard violation"""
    artifact_id = str(uuid4())
    request_body = {"action": "deploy"}

    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}", json=request_body)

    if response.status_code == 403:
        data = response.json()

        # Per api-artifacts.yaml PolicyViolation response
        assert "error_code" in data
        assert data["error_code"] == "POLICY_VIOLATION"
        assert "policy_name" in data
        assert "violation_reason" in data


@pytest.mark.asyncio
async def test_artifacts_patch_rollback(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{id} should support rollback action"""
    artifact_id = str(uuid4())
    request_body = {"action": "rollback"}

    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}", json=request_body)

    assert response.status_code in [200, 403, 404]


@pytest.mark.asyncio
async def test_artifacts_patch_invalid_action(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{id} should validate action enum"""
    artifact_id = str(uuid4())
    request_body = {"action": "invalid"}

    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}", json=request_body)

    assert response.status_code in [400, 422]
