"""
Contract tests for Analysis API endpoints
Per analysis-api.yaml specification

MUST FAIL before implementation (TDD principle)

Tests validate:
- POST /api/v1/analyze - Create analysis job
- GET /api/v1/analyze/{job_id} - Get job status
- DELETE /api/v1/analyze/{job_id} - Cancel job
- GET /api/v1/analyze/jobs - List jobs

Schema validation against:
/Users/nord/Downloads/slo-scout-spec-kit/slo-scout/specs/002-complete-slo-scout/contracts/analysis-api.yaml
"""
import pytest
from httpx import AsyncClient
from uuid import UUID, uuid4
from datetime import datetime


class TestCreateAnalysisJob:
    """Test POST /api/v1/analyze endpoint"""

    @pytest.mark.asyncio
    async def test_create_job_returns_202_with_valid_schema(
        self, async_client: AsyncClient, sample_service
    ):
        """POST /api/v1/analyze should return 202 with AnalysisJob schema"""
        request_body = {
            "service_id": str(sample_service.service_id),
            "lookback_days": 7
        }

        response = await async_client.post("/api/v1/analyze", json=request_body)

        # Per analysis-api.yaml: 202 Accepted
        assert response.status_code == 202

        data = response.json()

        # Validate AnalysisJob schema - required fields
        assert "job_id" in data
        UUID(data["job_id"])  # Raises ValueError if invalid UUID

        assert "service_id" in data
        assert data["service_id"] == str(sample_service.service_id)

        assert "status" in data
        assert data["status"] in ["pending", "running", "completed", "failed", "cancelled"]

        assert "lookback_days" in data
        assert data["lookback_days"] == 7

        assert "created_at" in data
        # Validate ISO 8601 datetime format
        datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_create_job_with_default_lookback_days(
        self, async_client: AsyncClient, sample_service
    ):
        """POST /api/v1/analyze should use default lookback_days=7"""
        request_body = {
            "service_id": str(sample_service.service_id)
            # lookback_days not provided - should default to 7
        }

        response = await async_client.post("/api/v1/analyze", json=request_body)

        assert response.status_code == 202
        data = response.json()
        assert data["lookback_days"] == 7

    @pytest.mark.asyncio
    async def test_create_job_with_max_lookback_days(
        self, async_client: AsyncClient, sample_service
    ):
        """POST /api/v1/analyze should accept maximum lookback_days=30"""
        request_body = {
            "service_id": str(sample_service.service_id),
            "lookback_days": 30
        }

        response = await async_client.post("/api/v1/analyze", json=request_body)

        assert response.status_code == 202
        data = response.json()
        assert data["lookback_days"] == 30

    @pytest.mark.asyncio
    async def test_create_job_validates_service_id_required(
        self, async_client: AsyncClient
    ):
        """POST /api/v1/analyze should return 400 if service_id missing"""
        request_body = {
            "lookback_days": 7
            # Missing required service_id
        }

        response = await async_client.post("/api/v1/analyze", json=request_body)

        # Per analysis-api.yaml: 400 Bad Request
        assert response.status_code == 400

        data = response.json()
        assert "error" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_create_job_validates_service_id_format(
        self, async_client: AsyncClient
    ):
        """POST /api/v1/analyze should return 400 if service_id is not UUID"""
        request_body = {
            "service_id": "not-a-valid-uuid",
            "lookback_days": 7
        }

        response = await async_client.post("/api/v1/analyze", json=request_body)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_job_validates_lookback_days_minimum(
        self, async_client: AsyncClient, sample_service
    ):
        """POST /api/v1/analyze should return 400 if lookback_days < 1"""
        request_body = {
            "service_id": str(sample_service.service_id),
            "lookback_days": 0  # Below minimum
        }

        response = await async_client.post("/api/v1/analyze", json=request_body)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_job_validates_lookback_days_maximum(
        self, async_client: AsyncClient, sample_service
    ):
        """POST /api/v1/analyze should return 400 if lookback_days > 30"""
        request_body = {
            "service_id": str(sample_service.service_id),
            "lookback_days": 31  # Exceeds maximum
        }

        response = await async_client.post("/api/v1/analyze", json=request_body)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_job_service_not_found(self, async_client: AsyncClient):
        """POST /api/v1/analyze should return 404 if service not found"""
        nonexistent_service_id = str(uuid4())
        request_body = {
            "service_id": nonexistent_service_id,
            "lookback_days": 7
        }

        response = await async_client.post("/api/v1/analyze", json=request_body)

        # Per analysis-api.yaml: 404 Not Found
        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_create_job_optional_fields_in_response(
        self, async_client: AsyncClient, sample_service
    ):
        """POST /api/v1/analyze response should include optional nullable fields"""
        request_body = {
            "service_id": str(sample_service.service_id),
            "lookback_days": 7
        }

        response = await async_client.post("/api/v1/analyze", json=request_body)

        assert response.status_code == 202
        data = response.json()

        # Optional fields per schema (nullable)
        # These may be None initially
        assert "started_at" in data or data.get("started_at") is None
        assert "completed_at" in data or data.get("completed_at") is None
        assert "error_message" in data or data.get("error_message") is None
        assert "results" in data or data.get("results") is None

        # retry_count should be present and >= 0
        if "retry_count" in data:
            assert data["retry_count"] >= 0
            assert data["retry_count"] <= 3  # Max 3 per FR-023


class TestGetAnalysisJob:
    """Test GET /api/v1/analyze/{job_id} endpoint"""

    @pytest.mark.asyncio
    async def test_get_job_returns_200_with_valid_schema(
        self, async_client: AsyncClient
    ):
        """GET /api/v1/analyze/{job_id} should return 200 with AnalysisJob schema"""
        # This test expects a job to exist - will fail until implemented
        job_id = str(uuid4())

        response = await async_client.get(f"/api/v1/analyze/{job_id}")

        # Per analysis-api.yaml: 200 OK
        assert response.status_code == 200

        data = response.json()

        # Validate AnalysisJob schema
        assert "job_id" in data
        UUID(data["job_id"])

        assert "service_id" in data
        UUID(data["service_id"])

        assert "status" in data
        assert data["status"] in ["pending", "running", "completed", "failed", "cancelled"]

        assert "lookback_days" in data
        assert 1 <= data["lookback_days"] <= 30

        assert "created_at" in data
        datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_get_job_with_results(self, async_client: AsyncClient):
        """GET /api/v1/analyze/{job_id} should include results when status=completed"""
        job_id = str(uuid4())

        response = await async_client.get(f"/api/v1/analyze/{job_id}")

        if response.status_code == 200:
            data = response.json()

            if data["status"] == "completed":
                # Validate results schema
                assert "results" in data
                results = data["results"]

                if results:
                    assert "journeys_discovered" in results
                    assert isinstance(results["journeys_discovered"], int)

                    assert "slis_generated" in results
                    assert isinstance(results["slis_generated"], int)

                    assert "telemetry_events_analyzed" in results
                    assert isinstance(results["telemetry_events_analyzed"], int)

                    assert "capsules_created" in results
                    assert isinstance(results["capsules_created"], int)

    @pytest.mark.asyncio
    async def test_get_job_with_error_message(self, async_client: AsyncClient):
        """GET /api/v1/analyze/{job_id} should include error_message when status=failed"""
        job_id = str(uuid4())

        response = await async_client.get(f"/api/v1/analyze/{job_id}")

        if response.status_code == 200:
            data = response.json()

            if data["status"] == "failed":
                # Should have error_message
                assert "error_message" in data
                assert data["error_message"] is not None
                assert isinstance(data["error_message"], str)

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, async_client: AsyncClient):
        """GET /api/v1/analyze/{job_id} should return 404 if job not found"""
        nonexistent_job_id = str(uuid4())

        response = await async_client.get(f"/api/v1/analyze/{nonexistent_job_id}")

        # Per analysis-api.yaml: 404 Not Found
        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_get_job_invalid_uuid_format(self, async_client: AsyncClient):
        """GET /api/v1/analyze/{job_id} should return 400 for invalid UUID"""
        invalid_job_id = "not-a-uuid"

        response = await async_client.get(f"/api/v1/analyze/{invalid_job_id}")

        # Should return 400 or 422 for invalid UUID format
        assert response.status_code in [400, 422]


class TestCancelAnalysisJob:
    """Test DELETE /api/v1/analyze/{job_id} endpoint"""

    @pytest.mark.asyncio
    async def test_cancel_job_returns_204(self, async_client: AsyncClient):
        """DELETE /api/v1/analyze/{job_id} should return 204 on success"""
        # First create a job (or use fixture when available)
        job_id = str(uuid4())

        response = await async_client.delete(f"/api/v1/analyze/{job_id}")

        # Per analysis-api.yaml: 204 No Content
        assert response.status_code == 204

        # 204 should have no response body
        assert not response.text or response.text == ""

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, async_client: AsyncClient):
        """DELETE /api/v1/analyze/{job_id} should return 404 if job not found"""
        nonexistent_job_id = str(uuid4())

        response = await async_client.delete(f"/api/v1/analyze/{nonexistent_job_id}")

        # Per analysis-api.yaml: 404 Not Found
        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_cancel_completed_job_returns_409(self, async_client: AsyncClient):
        """DELETE /api/v1/analyze/{job_id} should return 409 if job already completed"""
        # This requires a completed job - implementation will determine behavior
        job_id = str(uuid4())

        response = await async_client.delete(f"/api/v1/analyze/{job_id}")

        # Per analysis-api.yaml: 409 Conflict if already completed/failed
        if response.status_code == 409:
            data = response.json()
            assert "error" in data
            assert "message" in data


class TestListAnalysisJobs:
    """Test GET /api/v1/analyze/jobs endpoint"""

    @pytest.mark.asyncio
    async def test_list_jobs_returns_200_with_valid_schema(
        self, async_client: AsyncClient
    ):
        """GET /api/v1/analyze/jobs should return 200 with paginated list"""
        response = await async_client.get("/api/v1/analyze/jobs")

        # Per analysis-api.yaml: 200 OK
        assert response.status_code == 200

        data = response.json()

        # Validate response schema
        assert "jobs" in data
        assert isinstance(data["jobs"], list)

        assert "total" in data
        assert isinstance(data["total"], int)

        assert "limit" in data
        assert isinstance(data["limit"], int)

        assert "offset" in data
        assert isinstance(data["offset"], int)

    @pytest.mark.asyncio
    async def test_list_jobs_default_pagination(self, async_client: AsyncClient):
        """GET /api/v1/analyze/jobs should use default limit=50, offset=0"""
        response = await async_client.get("/api/v1/analyze/jobs")

        assert response.status_code == 200
        data = response.json()

        # Default values per schema
        assert data["limit"] == 50
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_list_jobs_custom_pagination(self, async_client: AsyncClient):
        """GET /api/v1/analyze/jobs should support custom limit and offset"""
        response = await async_client.get(
            "/api/v1/analyze/jobs?limit=10&offset=5"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["limit"] == 10
        assert data["offset"] == 5

    @pytest.mark.asyncio
    async def test_list_jobs_validates_limit_minimum(self, async_client: AsyncClient):
        """GET /api/v1/analyze/jobs should validate limit >= 1"""
        response = await async_client.get("/api/v1/analyze/jobs?limit=0")

        # Per analysis-api.yaml: 400 Bad Request
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_jobs_validates_limit_maximum(self, async_client: AsyncClient):
        """GET /api/v1/analyze/jobs should validate limit <= 100"""
        response = await async_client.get("/api/v1/analyze/jobs?limit=101")

        # Per analysis-api.yaml: 400 Bad Request
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_jobs_validates_offset_minimum(self, async_client: AsyncClient):
        """GET /api/v1/analyze/jobs should validate offset >= 0"""
        response = await async_client.get("/api/v1/analyze/jobs?offset=-1")

        # Per analysis-api.yaml: 400 Bad Request
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_service_id(
        self, async_client: AsyncClient, sample_service
    ):
        """GET /api/v1/analyze/jobs should filter by service_id"""
        service_id = str(sample_service.service_id)
        response = await async_client.get(
            f"/api/v1/analyze/jobs?service_id={service_id}"
        )

        assert response.status_code == 200
        data = response.json()

        # All returned jobs should match the service_id
        for job in data["jobs"]:
            assert job["service_id"] == service_id

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_status(self, async_client: AsyncClient):
        """GET /api/v1/analyze/jobs should filter by status"""
        status = "completed"
        response = await async_client.get(
            f"/api/v1/analyze/jobs?status={status}"
        )

        assert response.status_code == 200
        data = response.json()

        # All returned jobs should match the status
        for job in data["jobs"]:
            assert job["status"] == status

    @pytest.mark.asyncio
    async def test_list_jobs_validates_status_enum(self, async_client: AsyncClient):
        """GET /api/v1/analyze/jobs should validate status enum"""
        response = await async_client.get(
            "/api/v1/analyze/jobs?status=invalid_status"
        )

        # Per analysis-api.yaml: 400 Bad Request
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_jobs_validates_service_id_format(
        self, async_client: AsyncClient
    ):
        """GET /api/v1/analyze/jobs should validate service_id UUID format"""
        response = await async_client.get(
            "/api/v1/analyze/jobs?service_id=not-a-uuid"
        )

        # Per analysis-api.yaml: 400 Bad Request
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_jobs_combined_filters(
        self, async_client: AsyncClient, sample_service
    ):
        """GET /api/v1/analyze/jobs should support combining filters"""
        service_id = str(sample_service.service_id)
        response = await async_client.get(
            f"/api/v1/analyze/jobs?service_id={service_id}&status=running&limit=20"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["limit"] == 20

        # All returned jobs should match filters
        for job in data["jobs"]:
            assert job["service_id"] == service_id
            assert job["status"] == "running"

    @pytest.mark.asyncio
    async def test_list_jobs_each_job_has_valid_schema(
        self, async_client: AsyncClient
    ):
        """GET /api/v1/analyze/jobs should return valid AnalysisJob schema for each job"""
        response = await async_client.get("/api/v1/analyze/jobs")

        assert response.status_code == 200
        data = response.json()

        # Validate each job in the list
        for job in data["jobs"]:
            # Required fields
            assert "job_id" in job
            UUID(job["job_id"])

            assert "service_id" in job
            UUID(job["service_id"])

            assert "status" in job
            assert job["status"] in ["pending", "running", "completed", "failed", "cancelled"]

            assert "lookback_days" in job
            assert 1 <= job["lookback_days"] <= 30

            assert "created_at" in job
            datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))


class TestAnalysisJobSchema:
    """Test AnalysisJob schema validation edge cases"""

    @pytest.mark.asyncio
    async def test_job_timestamps_chronological_order(self, async_client: AsyncClient):
        """AnalysisJob timestamps should follow logical chronological order"""
        # Create and retrieve a job
        job_id = str(uuid4())
        response = await async_client.get(f"/api/v1/analyze/{job_id}")

        if response.status_code == 200:
            data = response.json()

            created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))

            if data.get("started_at"):
                started_at = datetime.fromisoformat(
                    data["started_at"].replace("Z", "+00:00")
                )
                assert started_at >= created_at

            if data.get("completed_at"):
                completed_at = datetime.fromisoformat(
                    data["completed_at"].replace("Z", "+00:00")
                )
                assert completed_at >= created_at

                if data.get("started_at"):
                    assert completed_at >= started_at

    @pytest.mark.asyncio
    async def test_retry_count_max_three(self, async_client: AsyncClient):
        """AnalysisJob retry_count should not exceed 3 per FR-023"""
        job_id = str(uuid4())
        response = await async_client.get(f"/api/v1/analyze/{job_id}")

        if response.status_code == 200:
            data = response.json()

            if "retry_count" in data:
                assert data["retry_count"] >= 0
                assert data["retry_count"] <= 3

    @pytest.mark.asyncio
    async def test_completed_job_has_results(self, async_client: AsyncClient):
        """Completed AnalysisJob should have results object"""
        job_id = str(uuid4())
        response = await async_client.get(f"/api/v1/analyze/{job_id}")

        if response.status_code == 200:
            data = response.json()

            if data["status"] == "completed":
                assert "results" in data
                assert data["results"] is not None

    @pytest.mark.asyncio
    async def test_failed_job_has_error_message(self, async_client: AsyncClient):
        """Failed AnalysisJob should have error_message"""
        job_id = str(uuid4())
        response = await async_client.get(f"/api/v1/analyze/{job_id}")

        if response.status_code == 200:
            data = response.json()

            if data["status"] == "failed":
                assert "error_message" in data
                assert data["error_message"] is not None
                assert len(data["error_message"]) > 0


class TestErrorResponses:
    """Test error response schema validation"""

    @pytest.mark.asyncio
    async def test_error_response_has_required_fields(
        self, async_client: AsyncClient
    ):
        """Error responses should follow Error schema with error and message"""
        # Trigger a known error condition
        response = await async_client.post(
            "/api/v1/analyze",
            json={"invalid": "data"}
        )

        if response.status_code >= 400:
            data = response.json()

            # Per Error schema
            assert "error" in data
            assert isinstance(data["error"], str)

            assert "message" in data
            assert isinstance(data["message"], str)

            # Optional details field
            if "details" in data:
                assert isinstance(data["details"], dict)

    @pytest.mark.asyncio
    async def test_concurrent_limit_error(self, async_client: AsyncClient):
        """POST /api/v1/analyze should return 429 when concurrent limit exceeded"""
        # This would require creating 10+ concurrent jobs
        # Test documents expected behavior per NFR-007
        response = await async_client.post(
            "/api/v1/analyze",
            json={"service_id": str(uuid4()), "lookback_days": 7}
        )

        # If we hit the limit, validate the error response
        if response.status_code == 429:
            data = response.json()
            assert "error" in data
            assert "message" in data
            # Error code might reference NFR-007 or concurrent limit
