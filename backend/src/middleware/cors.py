"""
CORS middleware for SLO-Scout API.

Implements T137: Configure CORS to allow frontend origin,
handle preflight OPTIONS requests properly.
"""
from typing import Optional, Union, Sequence
import logging
import re

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware as StarletteCORSMiddleware
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class CORSConfig(BaseModel):
    """CORS configuration settings."""

    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="List of allowed origins (exact match or regex patterns)"
    )
    allow_credentials: bool = Field(
        default=True,
        description="Allow cookies and authentication headers"
    )
    allowed_methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        description="Allowed HTTP methods"
    )
    allowed_headers: list[str] = Field(
        default_factory=lambda: [
            "Authorization",
            "Content-Type",
            "Accept",
            "Origin",
            "X-Requested-With",
            "X-Organization-ID",
        ],
        description="Allowed request headers"
    )
    exposed_headers: list[str] = Field(
        default_factory=lambda: [
            "X-Total-Count",
            "X-Page-Number",
            "X-Page-Size",
            "X-Request-ID",
        ],
        description="Headers exposed to browser"
    )
    max_age: int = Field(
        default=3600,
        description="Preflight cache duration in seconds"
    )


# Global config instance
cors_config = CORSConfig()


def is_origin_allowed(origin: str, allowed_origins: list[str]) -> bool:
    """
    Check if an origin is allowed.

    Supports exact match and regex patterns.

    Args:
        origin: Origin header value
        allowed_origins: List of allowed origins (exact or regex patterns)

    Returns:
        True if origin is allowed
    """
    # Special case: allow all
    if "*" in allowed_origins:
        return True

    # Check exact matches
    if origin in allowed_origins:
        return True

    # Check regex patterns
    for pattern in allowed_origins:
        if pattern.startswith("regex:"):
            regex_pattern = pattern[6:]  # Remove "regex:" prefix
            try:
                if re.match(regex_pattern, origin):
                    return True
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{pattern}': {e}")

    return False


class CORSMiddleware(BaseHTTPMiddleware):
    """
    Custom CORS middleware for SLO-Scout API.

    Handles preflight OPTIONS requests and adds appropriate CORS headers
    to responses based on configuration.
    """

    def __init__(
        self,
        app,
        config: Optional[CORSConfig] = None,
    ):
        """
        Initialize CORS middleware.

        Args:
            app: FastAPI application
            config: CORS configuration (uses global if not provided)
        """
        super().__init__(app)
        self.config = config or cors_config

        logger.info(
            f"CORS middleware initialized. "
            f"Allowed origins: {self.config.allowed_origins}, "
            f"Allow credentials: {self.config.allow_credentials}"
        )

    async def dispatch(self, request: Request, call_next):
        """
        Process request and add CORS headers to response.

        Args:
            request: FastAPI request
            call_next: Next middleware in chain

        Returns:
            Response with CORS headers
        """
        # Get origin from request
        origin = request.headers.get("origin")

        # Handle preflight OPTIONS request
        if request.method == "OPTIONS":
            return self._handle_preflight(request, origin)

        # Process normal request
        response = await call_next(request)

        # Add CORS headers to response
        if origin and is_origin_allowed(origin, self.config.allowed_origins):
            self._add_cors_headers(response, origin)
        elif not origin:
            # No origin header (e.g., same-origin request or non-browser client)
            logger.debug(f"No Origin header in request to {request.url.path}")
        else:
            logger.warning(
                f"Origin not allowed: {origin} for {request.url.path}. "
                f"Allowed origins: {self.config.allowed_origins}"
            )

        return response

    def _handle_preflight(self, request: Request, origin: Optional[str]) -> Response:
        """
        Handle preflight OPTIONS request.

        Args:
            request: FastAPI request
            origin: Origin header value

        Returns:
            Response with preflight CORS headers
        """
        # Check if origin is allowed
        if not origin or not is_origin_allowed(origin, self.config.allowed_origins):
            logger.warning(f"Preflight rejected for origin: {origin}")
            return Response(
                status_code=403,
                content="CORS preflight rejected: origin not allowed",
            )

        # Get requested method and headers
        requested_method = request.headers.get("access-control-request-method")
        requested_headers = request.headers.get("access-control-request-headers", "")

        # Validate requested method
        if requested_method and requested_method not in self.config.allowed_methods:
            logger.warning(
                f"Preflight rejected: method {requested_method} not allowed. "
                f"Allowed: {self.config.allowed_methods}"
            )
            return Response(
                status_code=403,
                content=f"CORS preflight rejected: method {requested_method} not allowed",
            )

        # Validate requested headers
        if requested_headers:
            headers_list = [h.strip().lower() for h in requested_headers.split(",")]
            allowed_headers_lower = [h.lower() for h in self.config.allowed_headers]

            for header in headers_list:
                if header not in allowed_headers_lower:
                    logger.warning(
                        f"Preflight rejected: header {header} not allowed. "
                        f"Allowed: {self.config.allowed_headers}"
                    )
                    return Response(
                        status_code=403,
                        content=f"CORS preflight rejected: header {header} not allowed",
                    )

        # Create preflight response
        response = Response(status_code=204)  # No Content

        # Add CORS headers
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = ", ".join(
            self.config.allowed_methods
        )
        response.headers["Access-Control-Allow-Headers"] = ", ".join(
            self.config.allowed_headers
        )
        response.headers["Access-Control-Max-Age"] = str(self.config.max_age)

        if self.config.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        logger.debug(
            f"Preflight approved for origin {origin}, "
            f"method {requested_method}, headers {requested_headers}"
        )

        return response

    def _add_cors_headers(self, response: Response, origin: str) -> None:
        """
        Add CORS headers to response.

        Args:
            response: Response object
            origin: Origin header value
        """
        response.headers["Access-Control-Allow-Origin"] = origin

        if self.config.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        if self.config.exposed_headers:
            response.headers["Access-Control-Expose-Headers"] = ", ".join(
                self.config.exposed_headers
            )


def configure_cors(
    app,
    allowed_origins: Optional[list[str]] = None,
    allow_credentials: bool = True,
    allowed_methods: Optional[list[str]] = None,
    allowed_headers: Optional[list[str]] = None,
    exposed_headers: Optional[list[str]] = None,
    max_age: int = 3600,
    use_starlette: bool = False,
) -> None:
    """
    Configure CORS for FastAPI application.

    This helper function makes it easy to add CORS support to the app.

    Usage:
        from fastapi import FastAPI
        from middleware.cors import configure_cors

        app = FastAPI()

        configure_cors(
            app,
            allowed_origins=[
                "http://localhost:3000",
                "https://slo-scout.example.com",
            ],
            allow_credentials=True
        )

    Args:
        app: FastAPI application
        allowed_origins: List of allowed origins
        allow_credentials: Allow cookies and auth headers
        allowed_methods: Allowed HTTP methods
        allowed_headers: Allowed request headers
        exposed_headers: Headers exposed to browser
        max_age: Preflight cache duration
        use_starlette: Use Starlette's built-in CORSMiddleware instead of custom
    """
    config = CORSConfig(
        allowed_origins=allowed_origins or ["http://localhost:3000"],
        allow_credentials=allow_credentials,
        allowed_methods=allowed_methods or ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allowed_headers=allowed_headers or [
            "Authorization",
            "Content-Type",
            "Accept",
            "Origin",
            "X-Requested-With",
            "X-Organization-ID",
        ],
        exposed_headers=exposed_headers or [
            "X-Total-Count",
            "X-Page-Number",
            "X-Page-Size",
            "X-Request-ID",
        ],
        max_age=max_age,
    )

    if use_starlette:
        # Use Starlette's built-in CORSMiddleware
        logger.info("Using Starlette CORSMiddleware")
        app.add_middleware(
            StarletteCORSMiddleware,
            allow_origins=config.allowed_origins,
            allow_credentials=config.allow_credentials,
            allow_methods=config.allowed_methods,
            allow_headers=config.allowed_headers,
            expose_headers=config.exposed_headers,
            max_age=config.max_age,
        )
    else:
        # Use custom CORSMiddleware
        logger.info("Using custom CORSMiddleware")
        app.add_middleware(CORSMiddleware, config=config)


# Environment-specific CORS configurations
def get_production_cors_config() -> CORSConfig:
    """
    Get CORS configuration for production environment.

    Returns:
        CORSConfig with production settings
    """
    return CORSConfig(
        allowed_origins=[
            "https://slo-scout.example.com",
            "https://app.slo-scout.example.com",
        ],
        allow_credentials=True,
        allowed_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allowed_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Organization-ID",
        ],
        exposed_headers=[
            "X-Total-Count",
            "X-Page-Number",
            "X-Page-Size",
            "X-Request-ID",
        ],
        max_age=86400,  # 24 hours
    )


def get_development_cors_config() -> CORSConfig:
    """
    Get CORS configuration for development environment.

    Returns:
        CORSConfig with development settings (more permissive)
    """
    return CORSConfig(
        allowed_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "regex:http://localhost:\\d+",  # Allow any localhost port
        ],
        allow_credentials=True,
        allowed_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allowed_headers=["*"],  # Allow all headers in development
        exposed_headers=[
            "X-Total-Count",
            "X-Page-Number",
            "X-Page-Size",
            "X-Request-ID",
        ],
        max_age=3600,  # 1 hour
    )


def get_cors_config_from_env() -> CORSConfig:
    """
    Get CORS configuration from environment variables.

    Environment variables:
        CORS_ALLOWED_ORIGINS: Comma-separated list of origins
        CORS_ALLOW_CREDENTIALS: "true" or "false"
        CORS_ALLOWED_METHODS: Comma-separated list of methods
        CORS_ALLOWED_HEADERS: Comma-separated list of headers
        CORS_EXPOSED_HEADERS: Comma-separated list of headers
        CORS_MAX_AGE: Integer seconds

    Returns:
        CORSConfig from environment or defaults
    """
    import os

    allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
    allowed_methods = os.getenv(
        "CORS_ALLOWED_METHODS",
        "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    )
    allowed_headers = os.getenv(
        "CORS_ALLOWED_HEADERS",
        "Authorization,Content-Type,Accept,Origin,X-Requested-With,X-Organization-ID"
    )
    exposed_headers = os.getenv(
        "CORS_EXPOSED_HEADERS",
        "X-Total-Count,X-Page-Number,X-Page-Size,X-Request-ID"
    )
    max_age = int(os.getenv("CORS_MAX_AGE", "3600"))

    return CORSConfig(
        allowed_origins=[o.strip() for o in allowed_origins.split(",")],
        allow_credentials=allow_credentials,
        allowed_methods=[m.strip() for m in allowed_methods.split(",")],
        allowed_headers=[h.strip() for h in allowed_headers.split(",")],
        exposed_headers=[h.strip() for h in exposed_headers.split(",")],
        max_age=max_age,
    )
