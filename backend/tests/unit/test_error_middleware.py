"""
Unit tests for error handling middleware.

Tests T136: Exception catching and structured Error responses
matching API contract Error schema.
"""
import pytest
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError

from src.middleware.errors import (
    ErrorHandlingMiddleware,
    ErrorResponse,
    ErrorCode,
    create_error_response,
    SLOScoutException,
    ResourceNotFoundError,
    InvalidStateTransitionError,
    ExternalServiceError,
)


@pytest.fixture
def app():
    """Create test FastAPI application."""
    app = FastAPI()

    @app.get("/success")
    async def success():
        return {"message": "success"}

    @app.get("/http-error")
    async def http_error():
        raise HTTPException(status_code=404, detail="Not found")

    @app.get("/custom-error")
    async def custom_error():
        raise ResourceNotFoundError(resource_type="SLI", resource_id="sli-123")

    @app.get("/validation-error")
    async def validation_error():
        class TestModel(BaseModel):
            name: str

        # This will raise ValidationError
        TestModel(name=123)

    @app.get("/database-error")
    async def database_error():
        raise IntegrityError("statement", "params", "orig")

    @app.get("/unexpected-error")
    async def unexpected_error():
        raise ValueError("Something went wrong")

    @app.get("/invalid-state")
    async def invalid_state():
        raise InvalidStateTransitionError(
            resource_type="Artifact",
            current_state="pending",
            attempted_action="deploy",
        )

    @app.get("/external-service-error")
    async def external_service():
        raise ExternalServiceError(
            service_name="Prometheus",
            error_message="Connection timeout",
        )

    # Add error handling middleware
    app.add_middleware(
        ErrorHandlingMiddleware,
        include_stack_trace=False,
        log_all_errors=True,
    )

    return app


@pytest.fixture
def app_with_stack_trace():
    """Create test app with stack traces enabled."""
    app = FastAPI()

    @app.get("/error")
    async def error():
        raise ValueError("Test error")

    app.add_middleware(
        ErrorHandlingMiddleware,
        include_stack_trace=True,
        log_all_errors=True,
    )

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def client_with_stack_trace(app_with_stack_trace):
    """Create test client with stack traces."""
    return TestClient(app_with_stack_trace)


class TestErrorHandlingMiddleware:
    """Tests for error handling middleware."""

    def test_successful_request(self, client):
        """Test that successful requests pass through."""
        response = client.get("/success")
        assert response.status_code == 200
        assert response.json() == {"message": "success"}

    def test_http_exception_handling(self, client):
        """Test handling of HTTPException."""
        response = client.get("/http-error")
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == ErrorCode.NOT_FOUND
        assert "message" in data

    def test_custom_exception_handling(self, client):
        """Test handling of custom SLOScoutException."""
        response = client.get("/custom-error")
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == ErrorCode.NOT_FOUND
        assert "SLI not found" in data["message"]
        assert data["details"]["resource_type"] == "SLI"
        assert data["details"]["resource_id"] == "sli-123"

    def test_validation_error_handling(self, client):
        """Test handling of Pydantic ValidationError."""
        response = client.get("/validation-error")
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == ErrorCode.VALIDATION_ERROR

    def test_database_error_handling(self, client):
        """Test handling of database errors."""
        response = client.get("/database-error")
        assert response.status_code in [409, 503]
        data = response.json()
        assert data["error_code"] in [ErrorCode.CONFLICT, ErrorCode.DATABASE_ERROR]

    def test_unexpected_error_handling(self, client):
        """Test handling of unexpected errors."""
        response = client.get("/unexpected-error")
        assert response.status_code == 500
        data = response.json()
        assert data["error_code"] == ErrorCode.INTERNAL_ERROR
        assert "unexpected error" in data["message"].lower()

    def test_stack_trace_included_in_dev_mode(self, client_with_stack_trace):
        """Test that stack traces are included when enabled."""
        response = client_with_stack_trace.get("/error")
        assert response.status_code == 500
        data = response.json()
        assert "stack_trace" in data["details"]
        assert "Traceback" in data["details"]["stack_trace"]

    def test_stack_trace_not_included_by_default(self, client):
        """Test that stack traces are not included by default."""
        response = client.get("/unexpected-error")
        assert response.status_code == 500
        data = response.json()
        assert "stack_trace" not in data["details"]


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_error_response_structure(self):
        """Test ErrorResponse structure matches API contract."""
        error = ErrorResponse(
            error_code="TEST_ERROR",
            message="Test error message",
            details={"field": "value"},
        )

        assert error.error_code == "TEST_ERROR"
        assert error.message == "Test error message"
        assert error.details == {"field": "value"}

        # Verify it can be serialized to dict
        error_dict = error.model_dump()
        assert "error_code" in error_dict
        assert "message" in error_dict
        assert "details" in error_dict

    def test_error_response_default_details(self):
        """Test that details defaults to empty dict."""
        error = ErrorResponse(
            error_code="TEST_ERROR",
            message="Test message",
        )

        assert error.details == {}


class TestCreateErrorResponse:
    """Tests for create_error_response helper."""

    def test_create_basic_error_response(self):
        """Test creating basic error response."""
        response = create_error_response(
            error_code=ErrorCode.NOT_FOUND,
            message="Resource not found",
            status_code=404,
        )

        assert response.status_code == 404
        data = response.body.decode()
        assert ErrorCode.NOT_FOUND in data
        assert "Resource not found" in data

    def test_create_error_response_with_details(self):
        """Test creating error response with details."""
        response = create_error_response(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Validation failed",
            status_code=400,
            details={
                "field": "service_name",
                "issue": "required",
            },
        )

        assert response.status_code == 400
        import json
        data = json.loads(response.body)
        assert data["details"]["field"] == "service_name"
        assert data["details"]["issue"] == "required"


class TestResourceNotFoundError:
    """Tests for ResourceNotFoundError exception."""

    def test_resource_not_found_error(self, client):
        """Test ResourceNotFoundError formatting."""
        response = client.get("/custom-error")
        assert response.status_code == 404
        data = response.json()

        assert data["error_code"] == ErrorCode.NOT_FOUND
        assert "SLI" in data["message"]
        assert "sli-123" in data["message"]
        assert data["details"]["resource_type"] == "SLI"
        assert data["details"]["resource_id"] == "sli-123"

    def test_resource_not_found_error_creation(self):
        """Test creating ResourceNotFoundError."""
        error = ResourceNotFoundError(
            resource_type="Journey",
            resource_id="journey-456",
        )

        assert error.error_code == ErrorCode.NOT_FOUND
        assert error.status_code == 404
        assert "Journey" in error.message
        assert "journey-456" in error.message


class TestInvalidStateTransitionError:
    """Tests for InvalidStateTransitionError exception."""

    def test_invalid_state_transition_error(self, client):
        """Test InvalidStateTransitionError formatting."""
        response = client.get("/invalid-state")
        assert response.status_code == 422
        data = response.json()

        assert data["error_code"] == ErrorCode.INVALID_STATE_TRANSITION
        assert "pending" in data["message"]
        assert "deploy" in data["message"]

    def test_invalid_state_transition_error_creation(self):
        """Test creating InvalidStateTransitionError."""
        error = InvalidStateTransitionError(
            resource_type="SLO",
            current_state="draft",
            attempted_action="deploy",
        )

        assert error.error_code == ErrorCode.INVALID_STATE_TRANSITION
        assert error.status_code == 422
        assert "SLO" in error.message
        assert "draft" in error.message
        assert "deploy" in error.message


class TestExternalServiceError:
    """Tests for ExternalServiceError exception."""

    def test_external_service_error(self, client):
        """Test ExternalServiceError formatting."""
        response = client.get("/external-service-error")
        assert response.status_code == 503
        data = response.json()

        assert data["error_code"] == ErrorCode.EXTERNAL_SERVICE_ERROR
        assert "Prometheus" in data["message"]

    def test_external_service_error_creation(self):
        """Test creating ExternalServiceError."""
        error = ExternalServiceError(
            service_name="Grafana",
            error_message="API timeout",
        )

        assert error.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR
        assert error.status_code == 503
        assert "Grafana" in error.message
        assert error.details["service_name"] == "Grafana"
        assert error.details["error_message"] == "API timeout"


class TestSLOScoutException:
    """Tests for base SLOScoutException."""

    def test_custom_exception_creation(self):
        """Test creating custom SLOScoutException."""
        error = SLOScoutException(
            message="Custom error",
            error_code="CUSTOM_ERROR",
            status_code=418,
            details={"custom": "data"},
        )

        assert error.message == "Custom error"
        assert error.error_code == "CUSTOM_ERROR"
        assert error.status_code == 418
        assert error.details == {"custom": "data"}


class TestErrorCodes:
    """Tests for ErrorCode constants."""

    def test_error_codes_defined(self):
        """Test that common error codes are defined."""
        assert hasattr(ErrorCode, "VALIDATION_ERROR")
        assert hasattr(ErrorCode, "UNAUTHORIZED")
        assert hasattr(ErrorCode, "FORBIDDEN")
        assert hasattr(ErrorCode, "NOT_FOUND")
        assert hasattr(ErrorCode, "INTERNAL_ERROR")
        assert hasattr(ErrorCode, "DATABASE_ERROR")
        assert hasattr(ErrorCode, "EXTERNAL_SERVICE_ERROR")

    def test_error_codes_are_strings(self):
        """Test that error codes are string constants."""
        assert isinstance(ErrorCode.VALIDATION_ERROR, str)
        assert isinstance(ErrorCode.NOT_FOUND, str)
        assert isinstance(ErrorCode.INTERNAL_ERROR, str)
