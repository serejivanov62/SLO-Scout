"""
Unit tests for CORS middleware.

Tests T137: CORS configuration for frontend integration,
preflight request handling, and origin validation.
"""
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware.cors import (
    CORSMiddleware,
    CORSConfig,
    configure_cors,
    get_production_cors_config,
    get_development_cors_config,
    get_cors_config_from_env,
    is_origin_allowed,
)


@pytest.fixture
def app():
    """Create test FastAPI application."""
    app = FastAPI()

    @app.get("/api/v1/test")
    async def test_endpoint():
        return {"message": "test"}

    @app.post("/api/v1/test")
    async def test_post():
        return {"message": "created"}

    # Add CORS middleware
    config = CORSConfig(
        allowed_origins=[
            "http://localhost:3000",
            "https://app.example.com",
        ],
        allow_credentials=True,
        allowed_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allowed_headers=["Authorization", "Content-Type"],
        exposed_headers=["X-Total-Count"],
        max_age=3600,
    )
    app.add_middleware(CORSMiddleware, config=config)

    return app


@pytest.fixture
def app_with_wildcard():
    """Create test app that allows all origins."""
    app = FastAPI()

    @app.get("/api/v1/test")
    async def test_endpoint():
        return {"message": "test"}

    config = CORSConfig(allowed_origins=["*"])
    app.add_middleware(CORSMiddleware, config=config)

    return app


@pytest.fixture
def app_with_regex():
    """Create test app with regex origin patterns."""
    app = FastAPI()

    @app.get("/api/v1/test")
    async def test_endpoint():
        return {"message": "test"}

    config = CORSConfig(
        allowed_origins=[
            "regex:http://localhost:\\d+",
            "regex:https://.*\\.example\\.com",
        ]
    )
    app.add_middleware(CORSMiddleware, config=config)

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def client_wildcard(app_with_wildcard):
    """Create test client with wildcard origins."""
    return TestClient(app_with_wildcard)


@pytest.fixture
def client_regex(app_with_regex):
    """Create test client with regex origins."""
    return TestClient(app_with_regex)


class TestCORSMiddleware:
    """Tests for CORS middleware."""

    def test_preflight_request_allowed_origin(self, client):
        """Test preflight OPTIONS request from allowed origin."""
        response = client.options(
            "/api/v1/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

        assert response.status_code == 204
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
        assert "POST" in response.headers["Access-Control-Allow-Methods"]
        assert "Content-Type" in response.headers["Access-Control-Allow-Headers"]
        assert response.headers["Access-Control-Allow-Credentials"] == "true"
        assert int(response.headers["Access-Control-Max-Age"]) == 3600

    def test_preflight_request_denied_origin(self, client):
        """Test preflight request from non-allowed origin is denied."""
        response = client.options(
            "/api/v1/test",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.status_code == 403

    def test_preflight_request_denied_method(self, client):
        """Test preflight request with non-allowed method is denied."""
        response = client.options(
            "/api/v1/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "TRACE",
            },
        )

        assert response.status_code == 403

    def test_preflight_request_denied_header(self, client):
        """Test preflight request with non-allowed header is denied."""
        response = client.options(
            "/api/v1/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Custom-Header",
            },
        )

        assert response.status_code == 403

    def test_actual_request_adds_cors_headers(self, client):
        """Test that actual requests get CORS headers."""
        response = client.get(
            "/api/v1/test",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
        assert response.headers["Access-Control-Allow-Credentials"] == "true"

    def test_request_without_origin(self, client):
        """Test request without Origin header (same-origin or non-browser)."""
        response = client.get("/api/v1/test")

        assert response.status_code == 200
        # No CORS headers should be added
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_request_from_disallowed_origin(self, client):
        """Test request from non-allowed origin doesn't get CORS headers."""
        response = client.get(
            "/api/v1/test",
            headers={"Origin": "http://evil.com"},
        )

        assert response.status_code == 200
        # No CORS headers should be added
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_exposed_headers(self, client):
        """Test that exposed headers are included in response."""
        response = client.get(
            "/api/v1/test",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200
        assert "Access-Control-Expose-Headers" in response.headers
        assert "X-Total-Count" in response.headers["Access-Control-Expose-Headers"]


class TestWildcardOrigins:
    """Tests for wildcard origin configuration."""

    def test_wildcard_allows_all_origins(self, client_wildcard):
        """Test that wildcard allows any origin."""
        response = client_wildcard.get(
            "/api/v1/test",
            headers={"Origin": "http://any-origin.com"},
        )

        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://any-origin.com"

    def test_wildcard_preflight(self, client_wildcard):
        """Test preflight with wildcard origins."""
        response = client_wildcard.options(
            "/api/v1/test",
            headers={
                "Origin": "http://random-origin.com",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.status_code == 204
        assert response.headers["Access-Control-Allow-Origin"] == "http://random-origin.com"


class TestRegexOrigins:
    """Tests for regex pattern origin matching."""

    def test_regex_pattern_localhost_ports(self, client_regex):
        """Test regex pattern matching localhost with different ports."""
        # Should match http://localhost:3000
        response = client_regex.get(
            "/api/v1/test",
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"

        # Should match http://localhost:8080
        response = client_regex.get(
            "/api/v1/test",
            headers={"Origin": "http://localhost:8080"},
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8080"

    def test_regex_pattern_subdomain(self, client_regex):
        """Test regex pattern matching subdomains."""
        # Should match https://app.example.com
        response = client_regex.get(
            "/api/v1/test",
            headers={"Origin": "https://app.example.com"},
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://app.example.com"

        # Should match https://staging.example.com
        response = client_regex.get(
            "/api/v1/test",
            headers={"Origin": "https://staging.example.com"},
        )
        assert response.status_code == 200

    def test_regex_pattern_no_match(self, client_regex):
        """Test that non-matching origins are rejected."""
        response = client_regex.get(
            "/api/v1/test",
            headers={"Origin": "https://evil.com"},
        )
        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" not in response.headers


class TestIsOriginAllowed:
    """Tests for is_origin_allowed helper function."""

    def test_exact_match(self):
        """Test exact origin matching."""
        assert is_origin_allowed(
            "http://localhost:3000",
            ["http://localhost:3000", "https://example.com"],
        )

    def test_no_match(self):
        """Test origin not in list."""
        assert not is_origin_allowed(
            "http://evil.com",
            ["http://localhost:3000", "https://example.com"],
        )

    def test_wildcard_match(self):
        """Test wildcard matching."""
        assert is_origin_allowed("http://any-origin.com", ["*"])

    def test_regex_match(self):
        """Test regex pattern matching."""
        assert is_origin_allowed(
            "http://localhost:3000",
            ["regex:http://localhost:\\d+"],
        )

    def test_regex_no_match(self):
        """Test regex pattern not matching."""
        assert not is_origin_allowed(
            "https://localhost:3000",
            ["regex:http://localhost:\\d+"],
        )


class TestCORSConfig:
    """Tests for CORSConfig model."""

    def test_default_config(self):
        """Test default CORS configuration."""
        config = CORSConfig()

        assert "http://localhost:3000" in config.allowed_origins
        assert config.allow_credentials is True
        assert "GET" in config.allowed_methods
        assert "Authorization" in config.allowed_headers
        assert config.max_age == 3600

    def test_custom_config(self):
        """Test custom CORS configuration."""
        config = CORSConfig(
            allowed_origins=["https://example.com"],
            allow_credentials=False,
            allowed_methods=["GET", "POST"],
            allowed_headers=["Content-Type"],
            exposed_headers=["X-Custom"],
            max_age=7200,
        )

        assert config.allowed_origins == ["https://example.com"]
        assert config.allow_credentials is False
        assert config.allowed_methods == ["GET", "POST"]
        assert config.allowed_headers == ["Content-Type"]
        assert config.exposed_headers == ["X-Custom"]
        assert config.max_age == 7200


class TestConfigureCors:
    """Tests for configure_cors helper function."""

    def test_configure_cors_basic(self):
        """Test basic CORS configuration."""
        app = FastAPI()

        @app.get("/test")
        async def test():
            return {"message": "test"}

        configure_cors(
            app,
            allowed_origins=["http://localhost:3000"],
            allow_credentials=True,
        )

        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


class TestEnvironmentConfigs:
    """Tests for environment-specific configurations."""

    def test_production_config(self):
        """Test production CORS configuration."""
        config = get_production_cors_config()

        assert all(origin.startswith("https://") for origin in config.allowed_origins)
        assert config.allow_credentials is True
        assert config.max_age > 3600  # Longer cache in production

    def test_development_config(self):
        """Test development CORS configuration."""
        config = get_development_cors_config()

        assert any("localhost" in origin for origin in config.allowed_origins)
        assert config.allow_credentials is True

    def test_config_from_env(self, monkeypatch):
        """Test loading configuration from environment variables."""
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,https://example.com")
        monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
        monkeypatch.setenv("CORS_ALLOWED_METHODS", "GET,POST")
        monkeypatch.setenv("CORS_MAX_AGE", "7200")

        config = get_cors_config_from_env()

        assert "http://localhost:3000" in config.allowed_origins
        assert "https://example.com" in config.allowed_origins
        assert config.allow_credentials is True
        assert config.allowed_methods == ["GET", "POST"]
        assert config.max_age == 7200

    def test_config_from_env_defaults(self, monkeypatch):
        """Test that environment config uses defaults when not set."""
        # Clear any existing env vars
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        monkeypatch.delenv("CORS_ALLOW_CREDENTIALS", raising=False)

        config = get_cors_config_from_env()

        assert len(config.allowed_origins) > 0
        assert isinstance(config.allow_credentials, bool)
