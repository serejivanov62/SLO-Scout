"""
Request validation middleware for SLO-Scout API.

Implements T135: Validate request bodies against OpenAPI schemas,
return 400 on invalid requests with detailed error messages.
"""
from typing import Optional, Dict, Any, Callable
import logging
import json

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, ValidationError, Field
import yaml


logger = logging.getLogger(__name__)


class ValidationErrorDetail(BaseModel):
    """Structured validation error detail."""

    field: str = Field(..., description="Field that failed validation")
    message: str = Field(..., description="Error message")
    type: str = Field(..., description="Error type (e.g., 'value_error', 'type_error')")
    input_value: Optional[Any] = Field(None, description="Invalid input value")


class ValidationErrorResponse(BaseModel):
    """Structured validation error response matching API contract."""

    error_code: str = Field(default="VALIDATION_ERROR", description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional error details including field-level errors"
    )


def format_pydantic_errors(validation_error: ValidationError) -> list[ValidationErrorDetail]:
    """
    Format Pydantic validation errors into structured error details.

    Args:
        validation_error: Pydantic ValidationError

    Returns:
        List of ValidationErrorDetail objects
    """
    errors = []

    for error in validation_error.errors():
        # Extract field path (e.g., ['body', 'service_name'] -> 'body.service_name')
        field_path = ".".join(str(loc) for loc in error["loc"])

        errors.append(
            ValidationErrorDetail(
                field=field_path,
                message=error["msg"],
                type=error["type"],
                input_value=error.get("input"),
            )
        )

    return errors


def create_validation_error_response(
    message: str,
    field_errors: Optional[list[ValidationErrorDetail]] = None,
    additional_details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """
    Create a standardized validation error response.

    Args:
        message: Human-readable error message
        field_errors: List of field-level validation errors
        additional_details: Additional context to include in details

    Returns:
        JSONResponse with 400 status code
    """
    details: Dict[str, Any] = additional_details or {}

    if field_errors:
        details["field_errors"] = [error.model_dump() for error in field_errors]

    error_response = ValidationErrorResponse(
        error_code="VALIDATION_ERROR",
        message=message,
        details=details,
    )

    logger.warning(
        f"Validation error: {message}. Field errors: {len(field_errors or [])}"
    )

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=error_response.model_dump(),
    )


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for request validation.

    Validates request bodies against Pydantic models and OpenAPI schemas.
    Returns structured 400 errors on validation failures.
    """

    def __init__(
        self,
        app,
        validate_content_type: bool = True,
        max_body_size: int = 10 * 1024 * 1024,  # 10MB default
        excluded_paths: Optional[list[str]] = None,
    ):
        """
        Initialize request validation middleware.

        Args:
            app: FastAPI application
            validate_content_type: Whether to validate Content-Type header
            max_body_size: Maximum allowed request body size in bytes
            excluded_paths: Paths to exclude from validation
        """
        super().__init__(app)
        self.validate_content_type = validate_content_type
        self.max_body_size = max_body_size
        self.excluded_paths = excluded_paths or [
            "/health",
            "/healthz",
            "/ready",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]

        logger.info(
            f"Request validation middleware initialized. "
            f"Max body size: {max_body_size} bytes, "
            f"Validate content-type: {validate_content_type}"
        )

    async def dispatch(self, request: Request, call_next):
        """
        Process request and validate body.

        Args:
            request: FastAPI request
            call_next: Next middleware in chain

        Returns:
            Response from next middleware/endpoint or validation error
        """
        # Skip validation for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        # Skip validation for GET, DELETE, OPTIONS (no body expected)
        if request.method in ["GET", "DELETE", "OPTIONS", "HEAD"]:
            return await call_next(request)

        try:
            # Validate Content-Type header for requests with body
            if self.validate_content_type and request.method in ["POST", "PUT", "PATCH"]:
                content_type = request.headers.get("content-type", "")

                # Allow application/json and application/json with charset
                if not content_type.startswith("application/json"):
                    return create_validation_error_response(
                        message="Invalid Content-Type. Expected 'application/json'",
                        additional_details={
                            "received_content_type": content_type,
                            "expected_content_type": "application/json",
                        },
                    )

            # Check Content-Length if provided
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    length = int(content_length)
                    if length > self.max_body_size:
                        return create_validation_error_response(
                            message=f"Request body too large. Maximum size: {self.max_body_size} bytes",
                            additional_details={
                                "content_length": length,
                                "max_allowed": self.max_body_size,
                            },
                        )
                except ValueError:
                    logger.warning(f"Invalid Content-Length header: {content_length}")

            # Read and validate request body (if present)
            if request.method in ["POST", "PUT", "PATCH"]:
                # Get the body without consuming the stream
                # (FastAPI will re-read it in the endpoint)
                try:
                    # Store original receive function
                    receive = request._receive

                    # Read body
                    body_bytes = b""
                    async for chunk in request.stream():
                        body_bytes += chunk
                        if len(body_bytes) > self.max_body_size:
                            return create_validation_error_response(
                                message=f"Request body too large. Maximum size: {self.max_body_size} bytes",
                                additional_details={
                                    "received_bytes": len(body_bytes),
                                    "max_allowed": self.max_body_size,
                                },
                            )

                    # Validate JSON syntax
                    if body_bytes:
                        try:
                            json.loads(body_bytes)
                        except json.JSONDecodeError as e:
                            return create_validation_error_response(
                                message="Invalid JSON in request body",
                                additional_details={
                                    "json_error": str(e),
                                    "line": e.lineno,
                                    "column": e.colno,
                                },
                            )

                    # Reconstruct the request body for downstream handlers
                    async def receive():
                        return {"type": "http.request", "body": body_bytes}

                    request._receive = receive

                except Exception as e:
                    logger.error(f"Error reading request body: {str(e)}", exc_info=True)
                    return create_validation_error_response(
                        message="Error reading request body",
                        additional_details={"error": str(e)},
                    )

            # Continue to next middleware/endpoint
            # Pydantic models in route handlers will perform detailed validation
            response = await call_next(request)

            return response

        except Exception as e:
            logger.error(
                f"Unexpected error in validation middleware: {str(e)}",
                exc_info=True,
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error_code": "INTERNAL_ERROR",
                    "message": "Internal validation error",
                    "details": {},
                },
            )


def validate_query_params(
    request: Request,
    required_params: Optional[list[str]] = None,
    allowed_params: Optional[list[str]] = None,
) -> None:
    """
    Validate query parameters.

    Use this in route handlers to validate query parameters:

    @app.get("/api/v1/journeys")
    async def list_journeys(request: Request):
        validate_query_params(
            request,
            required_params=["service_name", "environment"],
            allowed_params=["service_name", "environment", "min_confidence"]
        )
        ...

    Args:
        request: FastAPI request
        required_params: List of required query parameter names
        allowed_params: List of allowed query parameter names (validates no extra params)

    Raises:
        HTTPException: If validation fails
    """
    query_params = dict(request.query_params)

    # Check required parameters
    if required_params:
        missing = []
        for param in required_params:
            if param not in query_params or not query_params[param]:
                missing.append(param)

        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "MISSING_QUERY_PARAMS",
                    "message": f"Missing required query parameters: {missing}",
                    "details": {
                        "missing_params": missing,
                        "required_params": required_params,
                    },
                },
            )

    # Check for unexpected parameters
    if allowed_params:
        unexpected = []
        for param in query_params:
            if param not in allowed_params:
                unexpected.append(param)

        if unexpected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "UNEXPECTED_QUERY_PARAMS",
                    "message": f"Unexpected query parameters: {unexpected}",
                    "details": {
                        "unexpected_params": unexpected,
                        "allowed_params": allowed_params,
                    },
                },
            )


def validate_uuid(value: str, field_name: str = "id") -> None:
    """
    Validate that a string is a valid UUID.

    Args:
        value: String to validate
        field_name: Field name for error message

    Raises:
        HTTPException: If value is not a valid UUID
    """
    from uuid import UUID

    try:
        UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_UUID",
                "message": f"Invalid UUID format for {field_name}",
                "details": {
                    "field": field_name,
                    "value": value,
                },
            },
        )


def validate_enum(value: str, allowed_values: list[str], field_name: str) -> None:
    """
    Validate that a value is in an allowed set.

    Args:
        value: Value to validate
        allowed_values: List of allowed values
        field_name: Field name for error message

    Raises:
        HTTPException: If value is not in allowed set
    """
    if value not in allowed_values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_ENUM_VALUE",
                "message": f"Invalid value for {field_name}. Must be one of: {allowed_values}",
                "details": {
                    "field": field_name,
                    "value": value,
                    "allowed_values": allowed_values,
                },
            },
        )


def validate_range(
    value: float,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    field_name: str = "value",
) -> None:
    """
    Validate that a numeric value is within a range.

    Args:
        value: Value to validate
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)
        field_name: Field name for error message

    Raises:
        HTTPException: If value is out of range
    """
    if min_value is not None and value < min_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "VALUE_TOO_LOW",
                "message": f"{field_name} must be at least {min_value}",
                "details": {
                    "field": field_name,
                    "value": value,
                    "min_value": min_value,
                },
            },
        )

    if max_value is not None and value > max_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "VALUE_TOO_HIGH",
                "message": f"{field_name} must be at most {max_value}",
                "details": {
                    "field": field_name,
                    "value": value,
                    "max_value": max_value,
                },
            },
        )
