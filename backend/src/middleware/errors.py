"""
Error handling middleware for SLO-Scout API.

Implements T136: Catch exceptions and return structured Error responses
matching the api-analyze.yaml Error schema.
"""
from typing import Optional, Dict, Any, Union
import logging
import traceback
from datetime import datetime

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError, IntegrityError


logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    """
    Structured error response matching API contract Error schema.

    All API errors should use this format for consistency.
    """

    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional error details and context"
    )


class ErrorDetail(BaseModel):
    """Detailed error information for logging and debugging."""

    timestamp: str = Field(..., description="Error timestamp (ISO 8601)")
    path: str = Field(..., description="Request path that caused the error")
    method: str = Field(..., description="HTTP method")
    error_type: str = Field(..., description="Error type/class name")
    stack_trace: Optional[str] = Field(None, description="Stack trace (only in dev mode)")


# Common error codes
class ErrorCode:
    """Standard error codes used across the API."""

    # Validation errors (400)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_UUID = "INVALID_UUID"
    INVALID_ENUM = "INVALID_ENUM_VALUE"
    INVALID_RANGE = "INVALID_RANGE"
    INVALID_WINDOW = "INVALID_WINDOW"

    # Authentication errors (401)
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"

    # Authorization errors (403)
    FORBIDDEN = "FORBIDDEN"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    POLICY_VIOLATION = "POLICY_VIOLATION"

    # Resource errors (404)
    NOT_FOUND = "NOT_FOUND"
    SERVICE_NOT_FOUND = "SERVICE_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOURNEY_NOT_FOUND = "JOURNEY_NOT_FOUND"
    SLI_NOT_FOUND = "SLI_NOT_FOUND"
    SLO_NOT_FOUND = "SLO_NOT_FOUND"
    ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"

    # Conflict errors (409)
    CONFLICT = "CONFLICT"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"

    # Business logic errors (422)
    UNPROCESSABLE_ENTITY = "UNPROCESSABLE_ENTITY"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    SLI_NOT_APPROVED = "SLI_NOT_APPROVED"
    ARTIFACT_NOT_VALIDATED = "ARTIFACT_NOT_VALIDATED"

    # Server errors (500)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"

    # Service unavailable (503)
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"


def create_error_response(
    error_code: str,
    message: str,
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> JSONResponse:
    """
    Create a standardized error response.

    Args:
        error_code: Machine-readable error code
        message: Human-readable error message
        status_code: HTTP status code
        details: Additional error details
        request: Optional request object for logging

    Returns:
        JSONResponse with error details
    """
    error_response = ErrorResponse(
        error_code=error_code,
        message=message,
        details=details or {},
    )

    # Log error
    log_level = logging.ERROR if status_code >= 500 else logging.WARNING
    logger.log(
        log_level,
        f"Error response: {error_code} - {message} (status={status_code})"
        + (f" path={request.url.path}" if request else ""),
        extra={"error_details": details} if details else None,
    )

    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(),
    )


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for centralized error handling.

    Catches all exceptions and returns structured error responses
    matching the API contract Error schema.
    """

    def __init__(
        self,
        app,
        include_stack_trace: bool = False,
        log_all_errors: bool = True,
    ):
        """
        Initialize error handling middleware.

        Args:
            app: FastAPI application
            include_stack_trace: Include stack traces in error responses (dev only)
            log_all_errors: Whether to log all errors (including 4xx)
        """
        super().__init__(app)
        self.include_stack_trace = include_stack_trace
        self.log_all_errors = log_all_errors

        logger.info(
            f"Error handling middleware initialized. "
            f"Include stack trace: {include_stack_trace}, "
            f"Log all errors: {log_all_errors}"
        )

    async def dispatch(self, request: Request, call_next):
        """
        Process request and handle any exceptions.

        Args:
            request: FastAPI request
            call_next: Next middleware in chain

        Returns:
            Response or error response
        """
        try:
            response = await call_next(request)
            return response

        except RequestValidationError as e:
            # Pydantic validation error (FastAPI)
            return self._handle_validation_error(e, request)

        except ValidationError as e:
            # Pydantic validation error (direct)
            return self._handle_pydantic_error(e, request)

        except StarletteHTTPException as e:
            # HTTP exceptions (raised by endpoints or middleware)
            return self._handle_http_exception(e, request)

        except SQLAlchemyError as e:
            # Database errors
            return self._handle_database_error(e, request)

        except Exception as e:
            # Unexpected errors
            return self._handle_unexpected_error(e, request)

    def _handle_validation_error(
        self,
        error: RequestValidationError,
        request: Request,
    ) -> JSONResponse:
        """Handle FastAPI request validation errors."""
        field_errors = []
        for err in error.errors():
            field_path = ".".join(str(loc) for loc in err["loc"])
            field_errors.append({
                "field": field_path,
                "message": err["msg"],
                "type": err["type"],
            })

        logger.warning(
            f"Validation error on {request.method} {request.url.path}: "
            f"{len(field_errors)} field errors"
        )

        return create_error_response(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"field_errors": field_errors},
            request=request,
        )

    def _handle_pydantic_error(
        self,
        error: ValidationError,
        request: Request,
    ) -> JSONResponse:
        """Handle Pydantic validation errors."""
        field_errors = []
        for err in error.errors():
            field_path = ".".join(str(loc) for loc in err["loc"])
            field_errors.append({
                "field": field_path,
                "message": err["msg"],
                "type": err["type"],
            })

        logger.warning(
            f"Pydantic validation error on {request.method} {request.url.path}: "
            f"{len(field_errors)} field errors"
        )

        return create_error_response(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Data validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"field_errors": field_errors},
            request=request,
        )

    def _handle_http_exception(
        self,
        error: StarletteHTTPException,
        request: Request,
    ) -> JSONResponse:
        """Handle HTTP exceptions raised by endpoints."""
        # Extract error code from detail if it's a dict
        error_code = ErrorCode.INTERNAL_ERROR
        message = str(error.detail)
        details = {}

        if isinstance(error.detail, dict):
            error_code = error.detail.get("error_code", error_code)
            message = error.detail.get("message", message)
            details = error.detail.get("details", {})
        else:
            # Map status code to error code
            if error.status_code == status.HTTP_400_BAD_REQUEST:
                error_code = ErrorCode.INVALID_REQUEST
            elif error.status_code == status.HTTP_401_UNAUTHORIZED:
                error_code = ErrorCode.UNAUTHORIZED
            elif error.status_code == status.HTTP_403_FORBIDDEN:
                error_code = ErrorCode.FORBIDDEN
            elif error.status_code == status.HTTP_404_NOT_FOUND:
                error_code = ErrorCode.NOT_FOUND
            elif error.status_code == status.HTTP_409_CONFLICT:
                error_code = ErrorCode.CONFLICT
            elif error.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
                error_code = ErrorCode.UNPROCESSABLE_ENTITY
            elif error.status_code >= 500:
                error_code = ErrorCode.INTERNAL_ERROR

        if self.log_all_errors or error.status_code >= 500:
            log_level = logging.ERROR if error.status_code >= 500 else logging.WARNING
            logger.log(
                log_level,
                f"HTTP exception on {request.method} {request.url.path}: "
                f"{error.status_code} - {message}"
            )

        return create_error_response(
            error_code=error_code,
            message=message,
            status_code=error.status_code,
            details=details,
            request=request,
        )

    def _handle_database_error(
        self,
        error: SQLAlchemyError,
        request: Request,
    ) -> JSONResponse:
        """Handle database errors."""
        logger.error(
            f"Database error on {request.method} {request.url.path}: {str(error)}",
            exc_info=True,
        )

        # Check for specific error types
        if isinstance(error, IntegrityError):
            return create_error_response(
                error_code=ErrorCode.CONFLICT,
                message="Database constraint violation",
                status_code=status.HTTP_409_CONFLICT,
                details={
                    "error_type": "IntegrityError",
                    "error_message": str(error.orig) if hasattr(error, 'orig') else str(error),
                },
                request=request,
            )

        # Generic database error
        return create_error_response(
            error_code=ErrorCode.DATABASE_ERROR,
            message="Database operation failed",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={
                "error_type": type(error).__name__,
            },
            request=request,
        )

    def _handle_unexpected_error(
        self,
        error: Exception,
        request: Request,
    ) -> JSONResponse:
        """Handle unexpected errors."""
        logger.error(
            f"Unexpected error on {request.method} {request.url.path}: {str(error)}",
            exc_info=True,
        )

        details: Dict[str, Any] = {
            "error_type": type(error).__name__,
        }

        # Include stack trace in development mode
        if self.include_stack_trace:
            details["stack_trace"] = traceback.format_exc()

        return create_error_response(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected error occurred",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            request=request,
        )


# Custom exception classes for business logic errors
class SLOScoutException(Exception):
    """Base exception for SLO-Scout application errors."""

    def __init__(
        self,
        message: str,
        error_code: str = ErrorCode.INTERNAL_ERROR,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


class ResourceNotFoundError(SLOScoutException):
    """Raised when a requested resource is not found."""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            error_code=ErrorCode.NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            details={
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )


class InvalidStateTransitionError(SLOScoutException):
    """Raised when attempting an invalid state transition."""

    def __init__(self, resource_type: str, current_state: str, attempted_action: str):
        super().__init__(
            message=f"Cannot {attempted_action} {resource_type} in state '{current_state}'",
            error_code=ErrorCode.INVALID_STATE_TRANSITION,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={
                "resource_type": resource_type,
                "current_state": current_state,
                "attempted_action": attempted_action,
            },
        )


class ExternalServiceError(SLOScoutException):
    """Raised when an external service call fails."""

    def __init__(self, service_name: str, error_message: str):
        super().__init__(
            message=f"External service error: {service_name}",
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={
                "service_name": service_name,
                "error_message": error_message,
            },
        )
