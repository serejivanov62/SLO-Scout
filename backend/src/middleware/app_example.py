"""
Example FastAPI application demonstrating all middleware components.

Shows how to integrate JWT authentication, request validation, error handling,
and CORS middleware in a production-ready FastAPI application.
"""
from fastapi import FastAPI, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional

from .auth import (
    JWTAuthenticationMiddleware,
    JWTConfig,
    UserIdentity,
    get_current_user,
    require_roles,
    require_permissions,
)
from .validation import (
    RequestValidationMiddleware,
    validate_query_params,
    validate_uuid,
)
from .errors import (
    ErrorHandlingMiddleware,
    ResourceNotFoundError,
)
from .cors import (
    CORSMiddleware,
    get_development_cors_config,
    get_production_cors_config,
)


# Create FastAPI app
app = FastAPI(
    title="SLO-Scout API",
    description="API for SLO recommendation and artifact generation",
    version="1.0.0",
)


# Request/Response Models
class AnalyzeRequest(BaseModel):
    """Request model for analysis endpoint."""

    service_name: str = Field(..., min_length=1, description="Service to analyze")
    environment: str = Field(..., pattern="^(prod|staging|dev)$", description="Environment")
    analysis_window_days: int = Field(30, ge=1, le=90, description="Historical window in days")
    force_refresh: bool = Field(False, description="Force refresh of analysis")


class AnalyzeResponse(BaseModel):
    """Response model for analysis endpoint."""

    job_id: str = Field(..., description="Analysis job ID")
    status: str = Field(..., description="Job status")
    estimated_duration_seconds: int = Field(..., description="Estimated completion time")


class UserProfile(BaseModel):
    """User profile response."""

    user_id: str
    username: str
    organization_id: Optional[str]
    roles: list[str]
    permissions: list[str]


# Health check endpoint (no authentication required)
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "slo-scout-api"}


# Public endpoint
@app.get("/api/v1/info", tags=["Public"])
async def get_info():
    """Get public API information."""
    return {
        "name": "SLO-Scout API",
        "version": "1.0.0",
        "documentation": "/docs",
    }


# Protected endpoint - requires authentication
@app.get("/api/v1/profile", tags=["Users"], response_model=UserProfile)
async def get_profile(user: UserIdentity = Depends(get_current_user)):
    """
    Get current user profile.

    Requires: Valid JWT token
    """
    return UserProfile(
        user_id=user.user_id,
        username=user.username,
        organization_id=user.organization_id,
        roles=user.roles,
        permissions=user.permissions,
    )


# Endpoint with role-based access control
@app.post("/api/v1/admin/reset", tags=["Admin"])
async def admin_reset(user: UserIdentity = Depends(require_roles("admin"))):
    """
    Admin-only endpoint.

    Requires: JWT token with 'admin' role
    """
    return {
        "message": "System reset initiated",
        "initiated_by": user.username,
    }


# Endpoint with permission-based access control
@app.post("/api/v1/analyze", tags=["Analysis"], response_model=AnalyzeResponse)
async def create_analysis(
    request: AnalyzeRequest,
    user: UserIdentity = Depends(require_permissions("slo:analyze")),
):
    """
    Trigger SLI/SLO analysis for a service.

    Requires: JWT token with 'slo:analyze' permission
    """
    # Request validation happens automatically via Pydantic model
    # User authentication and permission check happen via dependency

    # Business logic here
    job_id = "123e4567-e89b-12d3-a456-426614174000"

    return AnalyzeResponse(
        job_id=job_id,
        status="pending",
        estimated_duration_seconds=120,
    )


# Endpoint with manual query parameter validation
@app.get("/api/v1/journeys", tags=["Journeys"])
async def list_journeys(
    request: Request,
    user: UserIdentity = Depends(get_current_user),
):
    """
    List discovered user journeys.

    Requires: Valid JWT token
    Query params: service_name (required), environment (required), min_confidence (optional)
    """
    # Manual query parameter validation
    validate_query_params(
        request,
        required_params=["service_name", "environment"],
        allowed_params=["service_name", "environment", "min_confidence"],
    )

    service_name = request.query_params.get("service_name")
    environment = request.query_params.get("environment")
    min_confidence = float(request.query_params.get("min_confidence", "50"))

    # Business logic here
    return {
        "journeys": [],
        "total_count": 0,
        "filters": {
            "service_name": service_name,
            "environment": environment,
            "min_confidence": min_confidence,
        },
    }


# Endpoint with UUID validation
@app.get("/api/v1/sli/{sli_id}", tags=["SLI"])
async def get_sli(
    sli_id: str,
    user: UserIdentity = Depends(get_current_user),
):
    """
    Get SLI details by ID.

    Requires: Valid JWT token
    """
    # Validate UUID format
    validate_uuid(sli_id, "sli_id")

    # Simulate fetching SLI
    # In real implementation, query database
    # For demo, raise error if not found
    if sli_id == "not-found":
        raise ResourceNotFoundError(resource_type="SLI", resource_id=sli_id)

    return {
        "sli_id": sli_id,
        "name": "checkout-latency-p95",
        "metric_type": "latency",
        "confidence_score": 87.5,
    }


# Endpoint demonstrating access to request state
@app.get("/api/v1/debug/user", tags=["Debug"])
async def debug_user(request: Request):
    """
    Debug endpoint showing user from request state.

    Requires: Valid JWT token
    """
    # User identity is injected into request.state by JWTAuthenticationMiddleware
    user = request.state.user

    return {
        "user_id": user.user_id,
        "username": user.username,
        "organization_id": user.organization_id,
        "roles": user.roles,
        "permissions": user.permissions,
        "request_path": request.url.path,
        "request_method": request.method,
    }


# Configure middleware stack
# Order matters! Middleware is applied in reverse order (bottom to top execution)

# 1. Error handling (catches all exceptions from downstream middleware/routes)
app.add_middleware(
    ErrorHandlingMiddleware,
    include_stack_trace=False,  # Set to True in development
    log_all_errors=True,
)

# 2. CORS (handles preflight and adds CORS headers)
import os
environment = os.getenv("ENVIRONMENT", "development")

if environment == "production":
    cors_config = get_production_cors_config()
else:
    cors_config = get_development_cors_config()

app.add_middleware(CORSMiddleware, config=cors_config)

# 3. Request validation (validates Content-Type, body size, JSON syntax)
app.add_middleware(
    RequestValidationMiddleware,
    validate_content_type=True,
    max_body_size=10 * 1024 * 1024,  # 10MB
    excluded_paths=["/health", "/docs", "/redoc", "/openapi.json"],
)

# 4. JWT authentication (verifies tokens and injects user identity)
jwt_config = JWTConfig(
    secret_key=os.getenv("JWT_SECRET_KEY", "change-me-in-production"),
    algorithm="HS256",
    token_expiry_minutes=int(os.getenv("JWT_EXPIRY_MINUTES", "60")),
    issuer=os.getenv("JWT_ISSUER", "slo-scout"),
    audience=os.getenv("JWT_AUDIENCE", "slo-scout-api"),
)

app.add_middleware(
    JWTAuthenticationMiddleware,
    config=jwt_config,
    excluded_paths=["/health", "/api/v1/info", "/docs", "/redoc", "/openapi.json"],
)


# Example: Generate a test token for development
def generate_test_token():
    """Generate a test JWT token for development."""
    from .auth import create_access_token

    token = create_access_token(
        user_id="test-user-123",
        username="developer@example.com",
        organization_id="org-456",
        roles=["admin", "developer"],
        permissions=["slo:read", "slo:write", "slo:analyze"],
        config=jwt_config,
    )

    print("\n" + "=" * 80)
    print("Test JWT Token for Development")
    print("=" * 80)
    print(f"\nToken: {token}\n")
    print("Usage:")
    print('  curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/profile')
    print("\n" + "=" * 80 + "\n")

    return token


if __name__ == "__main__":
    import uvicorn

    # Generate test token for development
    if environment == "development":
        generate_test_token()

    # Run the app
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
