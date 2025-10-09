"""
Contract test for SLI API endpoints
Validates against /Users/nord/Downloads/slo-scout-spec-kit/slo-scout/specs/002-complete-slo-scout/contracts/sli-api.yaml

Tests:
- GET /api/v1/sli - List SLI recommendations
- GET /api/v1/sli/{sli_id} - Get specific SLI
- PATCH /api/v1/sli/{sli_id}/approve - Approve SLI

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4
from typing import Dict, Any


@pytest.mark.asyncio
class TestListSLIs:
    """Test GET /api/v1/sli endpoint per sli-api.yaml"""

    async def test_list_slis_returns_200(self, async_client: AsyncClient):
        """GET /api/v1/sli should return 200 with paginated results"""
        response = await async_client.get("/api/v1/sli")

        assert response.status_code == 200

        data = response.json()
        assert "slis" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

        assert isinstance(data["slis"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["limit"], int)
        assert isinstance(data["offset"], int)

    async def test_list_slis_filter_by_journey_id(self, async_client: AsyncClient):
        """GET /api/v1/sli should filter by journey_id UUID parameter"""
        journey_id = str(uuid4())
        params = {"journey_id": journey_id}

        response = await async_client.get("/api/v1/sli", params=params)

        assert response.status_code == 200
        data = response.json()

        # All returned SLIs should have matching journey_id
        for sli in data["slis"]:
            assert sli["journey_id"] == journey_id

    async def test_list_slis_filter_by_approved_status(self, async_client: AsyncClient):
        """GET /api/v1/sli should filter by approved boolean parameter"""
        params = {"approved": True}

        response = await async_client.get("/api/v1/sli", params=params)

        assert response.status_code == 200
        data = response.json()

        # All returned SLIs should be approved
        for sli in data["slis"]:
            assert sli["approved"] is True

    async def test_list_slis_filter_by_min_confidence(self, async_client: AsyncClient):
        """GET /api/v1/sli should filter by min_confidence threshold (0.0-1.0)"""
        params = {"min_confidence": 0.8}

        response = await async_client.get("/api/v1/sli", params=params)

        assert response.status_code == 200
        data = response.json()

        # All returned SLIs should meet minimum confidence
        for sli in data["slis"]:
            assert sli["confidence_score"] >= 0.8

    async def test_list_slis_pagination_limit(self, async_client: AsyncClient):
        """GET /api/v1/sli should respect limit parameter (1-100, default 50)"""
        params = {"limit": 10}

        response = await async_client.get("/api/v1/sli", params=params)

        assert response.status_code == 200
        data = response.json()

        assert data["limit"] == 10
        assert len(data["slis"]) <= 10

    async def test_list_slis_pagination_offset(self, async_client: AsyncClient):
        """GET /api/v1/sli should respect offset parameter (minimum 0)"""
        params = {"offset": 5}

        response = await async_client.get("/api/v1/sli", params=params)

        assert response.status_code == 200
        data = response.json()

        assert data["offset"] == 5

    async def test_list_slis_invalid_journey_id_returns_400(self, async_client: AsyncClient):
        """GET /api/v1/sli should return 400 for invalid journey_id format"""
        params = {"journey_id": "not-a-uuid"}

        response = await async_client.get("/api/v1/sli", params=params)

        assert response.status_code == 400
        data = response.json()

        assert "error" in data
        assert "message" in data

    async def test_list_slis_invalid_min_confidence_returns_400(self, async_client: AsyncClient):
        """GET /api/v1/sli should return 400 for min_confidence outside [0.0, 1.0]"""
        params = {"min_confidence": 1.5}

        response = await async_client.get("/api/v1/sli", params=params)

        assert response.status_code == 400
        data = response.json()

        assert "error" in data
        assert "message" in data

    async def test_list_slis_invalid_limit_returns_400(self, async_client: AsyncClient):
        """GET /api/v1/sli should return 400 for limit > 100"""
        params = {"limit": 150}

        response = await async_client.get("/api/v1/sli", params=params)

        assert response.status_code == 400
        data = response.json()

        assert "error" in data
        assert "message" in data

    async def test_list_slis_schema_validation(self, async_client: AsyncClient):
        """GET /api/v1/sli should return SLIs matching schema from sli-api.yaml"""
        response = await async_client.get("/api/v1/sli")

        assert response.status_code == 200
        data = response.json()

        if len(data["slis"]) > 0:
            sli = data["slis"][0]

            # Required fields per sli-api.yaml components/schemas/SLI
            required_fields = [
                "sli_id",
                "journey_id",
                "name",
                "promql_query",
                "confidence_score",
                "approved",
                "created_at"
            ]

            for field in required_fields:
                assert field in sli, f"Required field '{field}' missing from SLI schema"

            # Type validations
            assert isinstance(sli["sli_id"], str)
            assert isinstance(sli["journey_id"], str)
            assert isinstance(sli["name"], str)
            assert isinstance(sli["promql_query"], str)
            assert isinstance(sli["confidence_score"], (int, float))
            assert isinstance(sli["approved"], bool)
            assert isinstance(sli["created_at"], str)

            # Value constraints
            assert 0.0 <= sli["confidence_score"] <= 1.0
            assert 1 <= len(sli["name"]) <= 255

            # Optional nullable fields
            if "description" in sli and sli["description"] is not None:
                assert isinstance(sli["description"], str)

            if "approved_by" in sli and sli["approved_by"] is not None:
                assert isinstance(sli["approved_by"], str)

            if "approved_at" in sli and sli["approved_at"] is not None:
                assert isinstance(sli["approved_at"], str)


@pytest.mark.asyncio
class TestGetSLI:
    """Test GET /api/v1/sli/{sli_id} endpoint per sli-api.yaml"""

    async def test_get_sli_returns_200(self, async_client: AsyncClient, sample_sli):
        """GET /api/v1/sli/{sli_id} should return 200 with SLI details"""
        sli_id = str(sample_sli.sli_id)

        response = await async_client.get(f"/api/v1/sli/{sli_id}")

        assert response.status_code == 200

        data = response.json()

        # Verify it returns the requested SLI
        assert data["sli_id"] == sli_id

    async def test_get_sli_not_found_returns_404(self, async_client: AsyncClient):
        """GET /api/v1/sli/{sli_id} should return 404 for non-existent SLI"""
        non_existent_id = str(uuid4())

        response = await async_client.get(f"/api/v1/sli/{non_existent_id}")

        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert "message" in data

    async def test_get_sli_invalid_uuid_returns_400_or_404(self, async_client: AsyncClient):
        """GET /api/v1/sli/{sli_id} should return 400/404 for invalid UUID format"""
        invalid_id = "not-a-uuid"

        response = await async_client.get(f"/api/v1/sli/{invalid_id}")

        # Could be 400 (validation error) or 404 (not found)
        assert response.status_code in [400, 404]

    async def test_get_sli_schema_validation(self, async_client: AsyncClient, sample_sli):
        """GET /api/v1/sli/{sli_id} should return SLI matching schema from sli-api.yaml"""
        sli_id = str(sample_sli.sli_id)

        response = await async_client.get(f"/api/v1/sli/{sli_id}")

        assert response.status_code == 200
        data = response.json()

        # Required fields per sli-api.yaml components/schemas/SLI
        required_fields = [
            "sli_id",
            "journey_id",
            "name",
            "promql_query",
            "confidence_score",
            "approved",
            "created_at"
        ]

        for field in required_fields:
            assert field in data, f"Required field '{field}' missing from SLI schema"

        # Type validations
        assert isinstance(data["sli_id"], str)
        assert isinstance(data["journey_id"], str)
        assert isinstance(data["name"], str)
        assert isinstance(data["promql_query"], str)
        assert isinstance(data["confidence_score"], (int, float))
        assert isinstance(data["approved"], bool)
        assert isinstance(data["created_at"], str)

        # Value constraints
        assert 0.0 <= data["confidence_score"] <= 1.0
        assert 1 <= len(data["name"]) <= 255


@pytest.mark.asyncio
class TestApproveSLI:
    """Test PATCH /api/v1/sli/{sli_id}/approve endpoint per sli-api.yaml"""

    async def test_approve_sli_returns_200(self, async_client: AsyncClient, sample_sli):
        """PATCH /api/v1/sli/{sli_id}/approve should return 200 with updated SLI"""
        sli_id = str(sample_sli.sli_id)

        request_body = {
            "approved_by": "sre-engineer@example.com"
        }

        response = await async_client.patch(
            f"/api/v1/sli/{sli_id}/approve",
            json=request_body
        )

        assert response.status_code == 200

        data = response.json()

        # Verify approval was recorded
        assert data["sli_id"] == sli_id
        assert data["approved"] is True
        assert data["approved_by"] == "sre-engineer@example.com"
        assert "approved_at" in data
        assert data["approved_at"] is not None

    async def test_approve_sli_not_found_returns_404(self, async_client: AsyncClient):
        """PATCH /api/v1/sli/{sli_id}/approve should return 404 for non-existent SLI"""
        non_existent_id = str(uuid4())

        request_body = {
            "approved_by": "sre-engineer@example.com"
        }

        response = await async_client.patch(
            f"/api/v1/sli/{non_existent_id}/approve",
            json=request_body
        )

        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert "message" in data

    async def test_approve_sli_missing_approved_by_returns_400(self, async_client: AsyncClient, sample_sli):
        """PATCH /api/v1/sli/{sli_id}/approve should return 400 if approved_by missing"""
        sli_id = str(sample_sli.sli_id)

        request_body = {}  # Missing required field

        response = await async_client.patch(
            f"/api/v1/sli/{sli_id}/approve",
            json=request_body
        )

        assert response.status_code in [400, 422]

        data = response.json()
        assert "error" in data or "detail" in data

    async def test_approve_sli_empty_approved_by_returns_400(self, async_client: AsyncClient, sample_sli):
        """PATCH /api/v1/sli/{sli_id}/approve should return 400 for empty approved_by"""
        sli_id = str(sample_sli.sli_id)

        request_body = {
            "approved_by": ""  # Empty string violates minLength: 1
        }

        response = await async_client.patch(
            f"/api/v1/sli/{sli_id}/approve",
            json=request_body
        )

        assert response.status_code in [400, 422]

    async def test_approve_sli_too_long_approved_by_returns_400(self, async_client: AsyncClient, sample_sli):
        """PATCH /api/v1/sli/{sli_id}/approve should return 400 for approved_by > 255 chars"""
        sli_id = str(sample_sli.sli_id)

        request_body = {
            "approved_by": "a" * 256  # Exceeds maxLength: 255
        }

        response = await async_client.patch(
            f"/api/v1/sli/{sli_id}/approve",
            json=request_body
        )

        assert response.status_code in [400, 422]

    async def test_approve_sli_already_approved_returns_400(self, async_client: AsyncClient, sample_sli):
        """PATCH /api/v1/sli/{sli_id}/approve should return 400 if already approved"""
        sli_id = str(sample_sli.sli_id)

        # First approval
        request_body = {
            "approved_by": "sre-engineer@example.com"
        }

        first_response = await async_client.patch(
            f"/api/v1/sli/{sli_id}/approve",
            json=request_body
        )

        # Second approval attempt
        second_response = await async_client.patch(
            f"/api/v1/sli/{sli_id}/approve",
            json=request_body
        )

        # Should reject duplicate approval
        if first_response.status_code == 200:
            assert second_response.status_code == 400
            data = second_response.json()
            assert "error" in data
            assert "message" in data

    async def test_approve_sli_invalid_uuid_returns_400_or_404(self, async_client: AsyncClient):
        """PATCH /api/v1/sli/{sli_id}/approve should return 400/404 for invalid UUID"""
        invalid_id = "not-a-uuid"

        request_body = {
            "approved_by": "sre-engineer@example.com"
        }

        response = await async_client.patch(
            f"/api/v1/sli/{invalid_id}/approve",
            json=request_body
        )

        # Could be 400 (validation error) or 404 (not found)
        assert response.status_code in [400, 404]

    async def test_approve_sli_response_schema(self, async_client: AsyncClient, sample_sli):
        """PATCH /api/v1/sli/{sli_id}/approve should return complete SLI schema"""
        sli_id = str(sample_sli.sli_id)

        request_body = {
            "approved_by": "sre-engineer@example.com"
        }

        response = await async_client.patch(
            f"/api/v1/sli/{sli_id}/approve",
            json=request_body
        )

        if response.status_code == 200:
            data = response.json()

            # Should return full SLI object per schema
            required_fields = [
                "sli_id",
                "journey_id",
                "name",
                "promql_query",
                "confidence_score",
                "approved",
                "created_at"
            ]

            for field in required_fields:
                assert field in data, f"Required field '{field}' missing"

            # Approval-specific fields
            assert data["approved"] is True
            assert data["approved_by"] == "sre-engineer@example.com"
            assert "approved_at" in data
            assert data["approved_at"] is not None
            assert isinstance(data["approved_at"], str)


@pytest.mark.asyncio
class TestErrorSchemaValidation:
    """Test error responses match Error schema from sli-api.yaml"""

    async def test_error_schema_for_404(self, async_client: AsyncClient):
        """Error responses should match components/schemas/Error schema"""
        non_existent_id = str(uuid4())

        response = await async_client.get(f"/api/v1/sli/{non_existent_id}")

        if response.status_code == 404:
            data = response.json()

            # Required error fields per sli-api.yaml
            assert "error" in data
            assert "message" in data

            assert isinstance(data["error"], str)
            assert isinstance(data["message"], str)

            # Optional details field
            if "details" in data:
                assert isinstance(data["details"], dict)

    async def test_error_schema_for_400(self, async_client: AsyncClient):
        """400 errors should match Error schema"""
        params = {"min_confidence": 2.0}  # Invalid: exceeds 1.0

        response = await async_client.get("/api/v1/sli", params=params)

        if response.status_code == 400:
            data = response.json()

            assert "error" in data
            assert "message" in data

            assert isinstance(data["error"], str)
            assert isinstance(data["message"], str)
