"""
FastAPI middleware for SLO-Scout.
"""
from .policy_guard import (
    PolicyGuardMiddleware,
    PolicyGuardException,
    check_artifact_policy,
    check_batch_policy,
)
from .auth import (
    JWTAuthenticationMiddleware,
    JWTConfig,
    UserIdentity,
    get_current_user,
    require_roles,
    require_permissions,
    create_access_token,
    verify_token,
)
from .validation import (
    RequestValidationMiddleware,
    ValidationErrorResponse,
    validate_query_params,
    validate_uuid,
    validate_enum,
    validate_range,
)
from .errors import (
    ErrorHandlingMiddleware,
    ErrorResponse,
    ErrorCode,
    create_error_response,
    SLOScoutException,
    ResourceNotFoundError,
    InvalidStateTransitionError,
    ExternalServiceError,
)
from .cors import (
    CORSMiddleware,
    CORSConfig,
    configure_cors,
    get_production_cors_config,
    get_development_cors_config,
    get_cors_config_from_env,
)

__all__ = [
    # Policy Guard
    "PolicyGuardMiddleware",
    "PolicyGuardException",
    "check_artifact_policy",
    "check_batch_policy",
    # Authentication
    "JWTAuthenticationMiddleware",
    "JWTConfig",
    "UserIdentity",
    "get_current_user",
    "require_roles",
    "require_permissions",
    "create_access_token",
    "verify_token",
    # Validation
    "RequestValidationMiddleware",
    "ValidationErrorResponse",
    "validate_query_params",
    "validate_uuid",
    "validate_enum",
    "validate_range",
    # Error Handling
    "ErrorHandlingMiddleware",
    "ErrorResponse",
    "ErrorCode",
    "create_error_response",
    "SLOScoutException",
    "ResourceNotFoundError",
    "InvalidStateTransitionError",
    "ExternalServiceError",
    # CORS
    "CORSMiddleware",
    "CORSConfig",
    "configure_cors",
    "get_production_cors_config",
    "get_development_cors_config",
    "get_cors_config_from_env",
]
