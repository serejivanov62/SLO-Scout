"""
JWT authentication middleware for SLO-Scout API.

Implements T134: JWT bearer token verification, user identity extraction,
and injection into request context.
"""
from typing import Optional, Dict, Any
import logging
from datetime import datetime, timedelta

from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from jose import JWTError, jwt
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


# Configuration (should be loaded from environment in production)
class JWTConfig(BaseModel):
    """JWT configuration settings."""

    secret_key: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for JWT signing/verification"
    )
    algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm"
    )
    token_expiry_minutes: int = Field(
        default=60,
        description="Token expiration time in minutes"
    )
    issuer: str = Field(
        default="slo-scout",
        description="JWT issuer claim"
    )
    audience: str = Field(
        default="slo-scout-api",
        description="JWT audience claim"
    )


# Global config instance (should be injected via dependency injection in production)
jwt_config = JWTConfig()


class UserIdentity(BaseModel):
    """User identity extracted from JWT token."""

    user_id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Username or email")
    organization_id: Optional[str] = Field(None, description="Organization ID for multi-tenancy")
    roles: list[str] = Field(default_factory=list, description="User roles")
    permissions: list[str] = Field(default_factory=list, description="Specific permissions")

    class Config:
        frozen = True  # Immutable after creation


class TokenPayload(BaseModel):
    """JWT token payload structure."""

    sub: str = Field(..., description="Subject (user_id)")
    username: str = Field(..., description="Username")
    organization_id: Optional[str] = Field(None, description="Organization ID")
    roles: list[str] = Field(default_factory=list, description="User roles")
    permissions: list[str] = Field(default_factory=list, description="User permissions")
    exp: int = Field(..., description="Expiration timestamp")
    iat: int = Field(..., description="Issued at timestamp")
    iss: str = Field(..., description="Issuer")
    aud: str = Field(..., description="Audience")


def create_access_token(
    user_id: str,
    username: str,
    organization_id: Optional[str] = None,
    roles: Optional[list[str]] = None,
    permissions: Optional[list[str]] = None,
    config: Optional[JWTConfig] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        user_id: Unique user identifier
        username: Username or email
        organization_id: Optional organization ID for multi-tenancy
        roles: List of user roles
        permissions: List of user permissions
        config: JWT configuration (uses global if not provided)

    Returns:
        Encoded JWT token string
    """
    cfg = config or jwt_config

    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=cfg.token_expiry_minutes)

    payload = {
        "sub": user_id,
        "username": username,
        "organization_id": organization_id,
        "roles": roles or [],
        "permissions": permissions or [],
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
        "iss": cfg.issuer,
        "aud": cfg.audience,
    }

    token = jwt.encode(payload, cfg.secret_key, algorithm=cfg.algorithm)

    logger.info(
        f"Created JWT token for user {user_id} (username={username}, "
        f"org={organization_id}, expires_at={expires_at.isoformat()})"
    )

    return token


def verify_token(token: str, config: Optional[JWTConfig] = None) -> UserIdentity:
    """
    Verify JWT token and extract user identity.

    Args:
        token: JWT token string
        config: JWT configuration (uses global if not provided)

    Returns:
        UserIdentity with extracted claims

    Raises:
        HTTPException: If token is invalid, expired, or has invalid claims
    """
    cfg = config or jwt_config

    try:
        # Decode and verify token
        payload = jwt.decode(
            token,
            cfg.secret_key,
            algorithms=[cfg.algorithm],
            issuer=cfg.issuer,
            audience=cfg.audience,
        )

        # Validate payload structure
        token_data = TokenPayload(**payload)

        # Create user identity
        identity = UserIdentity(
            user_id=token_data.sub,
            username=token_data.username,
            organization_id=token_data.organization_id,
            roles=token_data.roles,
            permissions=token_data.permissions,
        )

        logger.debug(
            f"Successfully verified token for user {identity.user_id} "
            f"(username={identity.username}, org={identity.organization_id})"
        )

        return identity

    except JWTError as e:
        logger.warning(f"JWT verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def extract_token_from_header(authorization: Optional[str]) -> str:
    """
    Extract JWT token from Authorization header.

    Args:
        authorization: Authorization header value (e.g., "Bearer <token>")

    Returns:
        JWT token string

    Raises:
        HTTPException: If header is missing or malformed
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return parts[1]


class JWTAuthenticationMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for JWT authentication.

    Verifies JWT bearer tokens and injects user identity into request state.
    Protects all endpoints except those in the excluded paths list.
    """

    def __init__(
        self,
        app,
        config: Optional[JWTConfig] = None,
        excluded_paths: Optional[list[str]] = None
    ):
        """
        Initialize JWT authentication middleware.

        Args:
            app: FastAPI application
            config: JWT configuration (uses global if not provided)
            excluded_paths: List of paths that don't require authentication
                           (e.g., ["/health", "/docs", "/openapi.json"])
        """
        super().__init__(app)
        self.config = config or jwt_config
        self.excluded_paths = excluded_paths or [
            "/health",
            "/healthz",
            "/ready",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]

        logger.info(
            f"JWT authentication middleware initialized. "
            f"Excluded paths: {self.excluded_paths}"
        )

    async def dispatch(self, request: Request, call_next):
        """
        Process request and verify authentication.

        Args:
            request: FastAPI request
            call_next: Next middleware in chain

        Returns:
            Response from next middleware/endpoint
        """
        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            logger.debug(f"Skipping auth for excluded path: {request.url.path}")
            return await call_next(request)

        # Check for OPTIONS preflight requests (CORS)
        if request.method == "OPTIONS":
            logger.debug("Skipping auth for OPTIONS preflight request")
            return await call_next(request)

        # Extract token from Authorization header
        authorization = request.headers.get("Authorization")

        try:
            token = extract_token_from_header(authorization)

            # Verify token and extract user identity
            user_identity = verify_token(token, self.config)

            # Inject user identity into request state
            request.state.user = user_identity

            logger.debug(
                f"Authenticated request to {request.url.path} "
                f"for user {user_identity.user_id}"
            )

            # Continue to next middleware/endpoint
            response = await call_next(request)

            return response

        except HTTPException as e:
            # Log authentication failure
            logger.warning(
                f"Authentication failed for {request.url.path}: {e.detail}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error in auth middleware: {str(e)}",
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal authentication error"
            )


# FastAPI dependency for requiring authentication in specific routes
http_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = http_bearer,
    config: Optional[JWTConfig] = None
) -> UserIdentity:
    """
    FastAPI dependency for extracting current user from JWT token.

    Use this in route handlers that need user identity:

    @app.get("/api/v1/profile")
    async def get_profile(user: UserIdentity = Depends(get_current_user)):
        return {"user_id": user.user_id, "username": user.username}

    Args:
        credentials: HTTP bearer credentials from request
        config: JWT configuration (uses global if not provided)

    Returns:
        UserIdentity extracted from token

    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    return verify_token(token, config)


def require_roles(*required_roles: str):
    """
    Create a dependency that requires specific roles.

    Usage:
        @app.get("/admin/users")
        async def list_users(user: UserIdentity = Depends(require_roles("admin"))):
            return {"users": [...]}

    Args:
        required_roles: Required role names

    Returns:
        FastAPI dependency function
    """
    async def role_checker(user: UserIdentity = get_current_user) -> UserIdentity:
        user_roles = set(user.roles)
        required = set(required_roles)

        if not required.intersection(user_roles):
            logger.warning(
                f"Access denied for user {user.user_id}. "
                f"Required roles: {required}, user roles: {user_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {list(required)}"
            )

        return user

    return role_checker


def require_permissions(*required_permissions: str):
    """
    Create a dependency that requires specific permissions.

    Usage:
        @app.post("/api/v1/slo")
        async def create_slo(
            user: UserIdentity = Depends(require_permissions("slo:write"))
        ):
            return {"slo_id": "..."}

    Args:
        required_permissions: Required permission names

    Returns:
        FastAPI dependency function
    """
    async def permission_checker(user: UserIdentity = get_current_user) -> UserIdentity:
        user_perms = set(user.permissions)
        required = set(required_permissions)

        if not required.intersection(user_perms):
            logger.warning(
                f"Access denied for user {user.user_id}. "
                f"Required permissions: {required}, user permissions: {user_perms}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {list(required)}"
            )

        return user

    return permission_checker
