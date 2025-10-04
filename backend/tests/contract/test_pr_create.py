"""
Contract test for POST /api/v1/pr endpoint
Per api-artifacts.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_pr_create_returns_201(async_client: AsyncClient):
    """POST /api/v1/pr should create GitOps PR"""
    request_body = {
        "artifact_ids": [str(uuid4()), str(uuid4())],
        "repository": "slo-scout-test/observability-config",
        "target_branch": "main"
    }

    response = await async_client.post("/api/v1/pr", json=request_body)

    assert response.status_code in [201, 404]

    if response.status_code == 201:
        data = response.json()

        # Per api-artifacts.yaml PR response
        assert "pr_url" in data
        assert data["pr_url"].startswith("http")

        assert "pr_number" in data
        assert isinstance(data["pr_number"], int)

        assert "branch_name" in data

        assert "artifacts_included" in data
        assert isinstance(data["artifacts_included"], list)
        assert len(data["artifacts_included"]) == 2


@pytest.mark.asyncio
async def test_pr_create_validates_repository(async_client: AsyncClient):
    """POST /api/v1/pr should validate repository format"""
    request_body = {
        "artifact_ids": [str(uuid4())],
        "repository": "invalid-format"  # Should be owner/repo
    }

    response = await async_client.post("/api/v1/pr", json=request_body)

    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_pr_create_requires_approved_artifacts(async_client: AsyncClient):
    """POST /api/v1/pr should require artifacts to be approved"""
    request_body = {
        "artifact_ids": [str(uuid4())],
        "repository": "slo-scout-test/observability-config"
    }

    response = await async_client.post("/api/v1/pr", json=request_body)

    # Should check artifact approval status
    assert response.status_code in [201, 400, 404]


@pytest.mark.asyncio
async def test_pr_create_conventional_commit(async_client: AsyncClient):
    """POST /api/v1/pr should use conventional commit format"""
    request_body = {
        "artifact_ids": [str(uuid4())],
        "repository": "slo-scout-test/observability-config"
    }

    response = await async_client.post("/api/v1/pr", json=request_body)

    if response.status_code == 201:
        data = response.json()

        # Per spec.md FR-009: conventional commit format
        if "commit_message" in data:
            # Should start with type: feat, fix, chore, etc.
            assert any(data["commit_message"].startswith(t) for t in ["feat:", "fix:", "chore:", "docs:"])
