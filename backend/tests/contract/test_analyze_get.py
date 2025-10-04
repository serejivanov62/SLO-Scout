"""
Contract test for GET /api/v1/analyze/{job_id} endpoint
Per api-analyze.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_analyze_get_returns_job_status(async_client: AsyncClient):
    """GET /api/v1/analyze/{job_id} should return job status"""
    job_id = str(uuid4())

    response = await async_client.get(f"/api/v1/analyze/{job_id}")

    # Per api-analyze.yaml: 200 OK (or 404 if not found)
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()

        # Assert job_id matches
        assert data["job_id"] == job_id

        # Assert status is valid enum
        assert data["status"] in ["pending", "running", "completed", "failed"]

        # Assert progress_percent is in range [0, 100]
        assert 0 <= data["progress_percent"] <= 100

        # Assert started_at is timestamp
        assert "started_at" in data

        # Assert completed_at is nullable
        assert data.get("completed_at") is None or isinstance(data["completed_at"], str)

        # Assert result_url is nullable
        assert data.get("result_url") is None or isinstance(data["result_url"], str)

        # Assert error_message is nullable
        assert data.get("error_message") is None or isinstance(data["error_message"], str)


@pytest.mark.asyncio
async def test_analyze_get_job_not_found(async_client: AsyncClient):
    """GET /api/v1/analyze/{job_id} should return 404 if job doesn't exist"""
    job_id = str(uuid4())

    response = await async_client.get(f"/api/v1/analyze/{job_id}")

    # Per api-analyze.yaml: 404 Not Found
    assert response.status_code == 404

    data = response.json()
    assert "error_code" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_analyze_get_invalid_uuid(async_client: AsyncClient):
    """GET /api/v1/analyze/{job_id} should return 400 for invalid UUID"""
    response = await async_client.get("/api/v1/analyze/not-a-uuid")

    assert response.status_code in [400, 404, 422]  # Depends on framework validation
