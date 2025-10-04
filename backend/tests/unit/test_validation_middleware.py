"""
Unit tests for request validation middleware.

Tests T135: Request body validation against OpenAPI schemas,
400 error responses on invalid requests.
"""
import pytest
import json
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from src.middleware.validation import (
    RequestValidationMiddleware,
    ValidationErrorResponse,
    validate_query_params,
    validate_uuid,
    validate_enum,
    validate_range,
    format_pydantic_errors,
    create_validation_error_response,
)


@pytest.fixture
def app():
    """Create test FastAPI application."""
    app = FastAPI()

    # Define request models
    class AnalyzeRequest(BaseModel):
        service_name: str = Field(..., min_length=1)
        environment: str = Field(..., pattern="^(prod|staging|dev)$")
        analysis_window_days: Optional[int] = Field(30, ge=1, le=90)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/v1/analyze")
    async def analyze(request: AnalyzeRequest):
        return {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "status": "pending",
        }

    @app.get("/api/v1/journeys")
    async def list_journeys(request: Request):
        # Manual query param validation
        validate_query_params(
            request,
            required_params=["service_name", "environment"],
            allowed_params=["service_name", "environment", "min_confidence"],
        )
        return {"journeys": []}

    @app.get("/api/v1/sli/{sli_id}")
    async def get_sli(sli_id: str):
        # Validate UUID
        validate_uuid(sli_id, "sli_id")
        return {"sli_id": sli_id}

    # Add validation middleware
    app.add_middleware(
        RequestValidationMiddleware,
        validate_content_type=True,
        max_body_size=1024 * 1024,  # 1MB
        excluded_paths=["/health"],
    )

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestRequestValidationMiddleware:
    """Tests for request validation middleware."""

    def test_valid_post_request(self, client):
        """Test valid POST request passes validation."""
        response = client.post(
            "/api/v1/analyze",
            json={
                "service_name": "payments-api",
                "environment": "prod",
                "analysis_window_days": 30,
            },
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert "job_id" in response.json()

    def test_missing_required_field(self, client):
        """Test that missing required field returns 422."""
        response = client.post(
            "/api/v1/analyze",
            json={"environment": "prod"},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_invalid_field_value(self, client):
        """Test that invalid field value returns 422."""
        response = client.post(
            "/api/v1/analyze",
            json={
                "service_name": "payments-api",
                "environment": "invalid-env",  # Not in enum
                "analysis_window_days": 30,
            },
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_invalid_content_type(self, client):
        """Test that invalid Content-Type returns 400."""
        response = client.post(
            "/api/v1/analyze",
            data="not json",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert "Content-Type" in data["message"]

    def test_invalid_json_syntax(self, client):
        """Test that malformed JSON returns 400."""
        response = client.post(
            "/api/v1/analyze",
            content="{invalid json}",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert "Invalid JSON" in data["message"]

    def test_request_body_too_large(self, client):
        """Test that oversized request body returns 400."""
        # Create large payload (> 1MB)
        large_payload = {
            "service_name": "payments-api",
            "environment": "prod",
            "large_field": "x" * (2 * 1024 * 1024),  # 2MB
        }

        response = client.post(
            "/api/v1/analyze",
            json=large_payload,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "too large" in data["message"]

    def test_excluded_path_skips_validation(self, client):
        """Test that excluded paths skip validation."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_get_request_skips_body_validation(self, client):
        """Test that GET requests skip body validation."""
        response = client.get(
            "/api/v1/journeys",
            params={"service_name": "payments-api", "environment": "prod"},
        )
        assert response.status_code == 200


class TestValidateQueryParams:
    """Tests for query parameter validation."""

    def test_valid_query_params(self, client):
        """Test valid query parameters."""
        response = client.get(
            "/api/v1/journeys",
            params={
                "service_name": "payments-api",
                "environment": "prod",
            },
        )
        assert response.status_code == 200

    def test_missing_required_param(self, client):
        """Test that missing required param returns 400."""
        response = client.get(
            "/api/v1/journeys",
            params={"service_name": "payments-api"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Missing required query parameters" in data["detail"]["message"]

    def test_unexpected_query_param(self, client):
        """Test that unexpected param returns 400."""
        response = client.get(
            "/api/v1/journeys",
            params={
                "service_name": "payments-api",
                "environment": "prod",
                "unexpected_param": "value",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert "Unexpected query parameters" in data["detail"]["message"]

    def test_optional_query_param(self, client):
        """Test that optional query param is allowed."""
        response = client.get(
            "/api/v1/journeys",
            params={
                "service_name": "payments-api",
                "environment": "prod",
                "min_confidence": "50",
            },
        )
        assert response.status_code == 200


class TestValidateUUID:
    """Tests for UUID validation."""

    def test_valid_uuid(self, client):
        """Test valid UUID."""
        response = client.get("/api/v1/sli/123e4567-e89b-12d3-a456-426614174000")
        assert response.status_code == 200

    def test_invalid_uuid(self, client):
        """Test invalid UUID returns 400."""
        response = client.get("/api/v1/sli/not-a-uuid")
        assert response.status_code == 400
        data = response.json()
        assert "Invalid UUID format" in data["detail"]["message"]

    def test_uuid_with_hyphens(self, client):
        """Test UUID with hyphens is valid."""
        response = client.get("/api/v1/sli/550e8400-e29b-41d4-a716-446655440000")
        assert response.status_code == 200


class TestValidateEnum:
    """Tests for enum validation."""

    def test_validate_enum_valid_value(self):
        """Test validating valid enum value."""
        # Should not raise
        validate_enum("prod", ["prod", "staging", "dev"], "environment")

    def test_validate_enum_invalid_value(self):
        """Test validating invalid enum value raises error."""
        with pytest.raises(Exception) as exc_info:
            validate_enum("invalid", ["prod", "staging", "dev"], "environment")

        assert exc_info.value.status_code == 400
        assert "Invalid value for environment" in str(exc_info.value.detail)


class TestValidateRange:
    """Tests for range validation."""

    def test_validate_range_valid_value(self):
        """Test validating value within range."""
        # Should not raise
        validate_range(50, min_value=1, max_value=100, field_name="confidence")

    def test_validate_range_value_too_low(self):
        """Test that value below minimum raises error."""
        with pytest.raises(Exception) as exc_info:
            validate_range(0, min_value=1, max_value=100, field_name="confidence")

        assert exc_info.value.status_code == 400
        assert "must be at least 1" in str(exc_info.value.detail)

    def test_validate_range_value_too_high(self):
        """Test that value above maximum raises error."""
        with pytest.raises(Exception) as exc_info:
            validate_range(101, min_value=1, max_value=100, field_name="confidence")

        assert exc_info.value.status_code == 400
        assert "must be at most 100" in str(exc_info.value.detail)

    def test_validate_range_no_min(self):
        """Test validating range with no minimum."""
        # Should not raise
        validate_range(-10, max_value=100, field_name="value")

    def test_validate_range_no_max(self):
        """Test validating range with no maximum."""
        # Should not raise
        validate_range(1000, min_value=1, field_name="value")

    def test_validate_range_boundary_values(self):
        """Test that boundary values are valid (inclusive)."""
        # Should not raise
        validate_range(1, min_value=1, max_value=100)
        validate_range(100, min_value=1, max_value=100)


class TestValidationErrorResponse:
    """Tests for ValidationErrorResponse model."""

    def test_create_validation_error_response(self):
        """Test creating validation error response."""
        from src.middleware.validation import ValidationErrorDetail

        field_errors = [
            ValidationErrorDetail(
                field="service_name",
                message="Field required",
                type="value_error.missing",
            ),
        ]

        response = create_validation_error_response(
            message="Request validation failed",
            field_errors=field_errors,
        )

        assert response.status_code == 400
        data = json.loads(response.body)
        assert data["error_code"] == "VALIDATION_ERROR"
        assert data["message"] == "Request validation failed"
        assert "field_errors" in data["details"]
        assert len(data["details"]["field_errors"]) == 1

    def test_validation_error_response_structure(self):
        """Test ValidationErrorResponse structure."""
        error = ValidationErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Invalid request",
            details={"field": "value"},
        )

        assert error.error_code == "VALIDATION_ERROR"
        assert error.message == "Invalid request"
        assert error.details == {"field": "value"}


class TestFormatPydanticErrors:
    """Tests for Pydantic error formatting."""

    def test_format_pydantic_errors(self):
        """Test formatting Pydantic validation errors."""
        from pydantic import BaseModel, Field, ValidationError

        class TestModel(BaseModel):
            name: str = Field(..., min_length=1)
            age: int = Field(..., ge=0)

        try:
            TestModel(name="", age=-1)
        except ValidationError as e:
            errors = format_pydantic_errors(e)

            assert len(errors) >= 1
            assert all(hasattr(err, "field") for err in errors)
            assert all(hasattr(err, "message") for err in errors)
            assert all(hasattr(err, "type") for err in errors)
