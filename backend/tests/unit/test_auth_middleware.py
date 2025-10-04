"""
Unit tests for JWT authentication middleware.

Tests T134: JWT bearer token verification, user identity extraction,
and request context injection.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from jose import jwt

from fastapi import FastAPI, Request, Depends
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from src.middleware.auth import (
    JWTAuthenticationMiddleware,
    JWTConfig,
    UserIdentity,
    create_access_token,
    verify_token,
    get_current_user,
    require_roles,
    require_permissions,
    extract_token_from_header,
)


# Test configuration
TEST_JWT_CONFIG = JWTConfig(
    secret_key="test-secret-key-do-not-use-in-production",
    algorithm="HS256",
    token_expiry_minutes=60,
    issuer="test-slo-scout",
    audience="test-api",
)


@pytest.fixture
def app():
    """Create test FastAPI application."""
    app = FastAPI()

    @app.get("/public")
    async def public_endpoint():
        return {"message": "public"}

    @app.get("/protected")
    async def protected_endpoint(request: Request):
        # Access user from request state
        user = request.state.user
        return {
            "message": "protected",
            "user_id": user.user_id,
            "username": user.username,
        }

    @app.get("/admin")
    async def admin_endpoint(user: UserIdentity = Depends(require_roles("admin"))):
        return {"message": "admin", "user_id": user.user_id}

    @app.get("/with-permission")
    async def permission_endpoint(
        user: UserIdentity = Depends(require_permissions("slo:write"))
    ):
        return {"message": "permission", "user_id": user.user_id}

    # Add authentication middleware
    app.add_middleware(
        JWTAuthenticationMiddleware,
        config=TEST_JWT_CONFIG,
        excluded_paths=["/public", "/health"],
    )

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def valid_token():
    """Create a valid JWT token."""
    return create_access_token(
        user_id="user-123",
        username="test@example.com",
        organization_id="org-456",
        roles=["user"],
        permissions=["slo:read"],
        config=TEST_JWT_CONFIG,
    )


@pytest.fixture
def admin_token():
    """Create a valid admin JWT token."""
    return create_access_token(
        user_id="admin-123",
        username="admin@example.com",
        organization_id="org-456",
        roles=["admin"],
        permissions=["slo:read", "slo:write"],
        config=TEST_JWT_CONFIG,
    )


class TestCreateAccessToken:
    """Tests for JWT token creation."""

    def test_create_token_basic(self):
        """Test creating a basic JWT token."""
        token = create_access_token(
            user_id="user-123",
            username="test@example.com",
            config=TEST_JWT_CONFIG,
        )

        assert token is not None
        assert isinstance(token, str)

        # Decode token to verify contents
        payload = jwt.decode(
            token,
            TEST_JWT_CONFIG.secret_key,
            algorithms=[TEST_JWT_CONFIG.algorithm],
            issuer=TEST_JWT_CONFIG.issuer,
            audience=TEST_JWT_CONFIG.audience,
        )

        assert payload["sub"] == "user-123"
        assert payload["username"] == "test@example.com"
        assert payload["organization_id"] is None
        assert payload["roles"] == []
        assert payload["permissions"] == []

    def test_create_token_with_roles_and_permissions(self):
        """Test creating token with roles and permissions."""
        token = create_access_token(
            user_id="user-123",
            username="test@example.com",
            organization_id="org-456",
            roles=["admin", "developer"],
            permissions=["slo:read", "slo:write"],
            config=TEST_JWT_CONFIG,
        )

        payload = jwt.decode(
            token,
            TEST_JWT_CONFIG.secret_key,
            algorithms=[TEST_JWT_CONFIG.algorithm],
        )

        assert payload["organization_id"] == "org-456"
        assert set(payload["roles"]) == {"admin", "developer"}
        assert set(payload["permissions"]) == {"slo:read", "slo:write"}

    def test_token_expiration(self):
        """Test that token includes correct expiration."""
        before = datetime.utcnow()
        token = create_access_token(
            user_id="user-123",
            username="test@example.com",
            config=TEST_JWT_CONFIG,
        )
        after = datetime.utcnow()

        payload = jwt.decode(
            token,
            TEST_JWT_CONFIG.secret_key,
            algorithms=[TEST_JWT_CONFIG.algorithm],
        )

        # Check expiration is approximately token_expiry_minutes from now
        expected_exp = before + timedelta(minutes=TEST_JWT_CONFIG.token_expiry_minutes)
        actual_exp = datetime.fromtimestamp(payload["exp"])

        # Allow 2 second tolerance
        assert abs((actual_exp - expected_exp).total_seconds()) < 2


class TestVerifyToken:
    """Tests for JWT token verification."""

    def test_verify_valid_token(self, valid_token):
        """Test verifying a valid token."""
        identity = verify_token(valid_token, TEST_JWT_CONFIG)

        assert isinstance(identity, UserIdentity)
        assert identity.user_id == "user-123"
        assert identity.username == "test@example.com"
        assert identity.organization_id == "org-456"
        assert identity.roles == ["user"]
        assert identity.permissions == ["slo:read"]

    def test_verify_expired_token(self):
        """Test that expired tokens are rejected."""
        # Create token that expired 1 hour ago
        now = datetime.utcnow()
        expired_time = now - timedelta(hours=1)

        payload = {
            "sub": "user-123",
            "username": "test@example.com",
            "organization_id": None,
            "roles": [],
            "permissions": [],
            "exp": int(expired_time.timestamp()),
            "iat": int((expired_time - timedelta(hours=1)).timestamp()),
            "iss": TEST_JWT_CONFIG.issuer,
            "aud": TEST_JWT_CONFIG.audience,
        }

        token = jwt.encode(payload, TEST_JWT_CONFIG.secret_key, algorithm=TEST_JWT_CONFIG.algorithm)

        with pytest.raises(Exception) as exc_info:
            verify_token(token, TEST_JWT_CONFIG)

        assert exc_info.value.status_code == 401

    def test_verify_invalid_signature(self):
        """Test that tokens with invalid signatures are rejected."""
        # Create token with different secret
        wrong_config = JWTConfig(
            secret_key="wrong-secret",
            algorithm="HS256",
            issuer=TEST_JWT_CONFIG.issuer,
            audience=TEST_JWT_CONFIG.audience,
        )

        token = create_access_token(
            user_id="user-123",
            username="test@example.com",
            config=wrong_config,
        )

        with pytest.raises(Exception) as exc_info:
            verify_token(token, TEST_JWT_CONFIG)

        assert exc_info.value.status_code == 401

    def test_verify_invalid_issuer(self):
        """Test that tokens with invalid issuer are rejected."""
        wrong_config = JWTConfig(
            secret_key=TEST_JWT_CONFIG.secret_key,
            algorithm="HS256",
            issuer="wrong-issuer",
            audience=TEST_JWT_CONFIG.audience,
        )

        token = create_access_token(
            user_id="user-123",
            username="test@example.com",
            config=wrong_config,
        )

        with pytest.raises(Exception) as exc_info:
            verify_token(token, TEST_JWT_CONFIG)

        assert exc_info.value.status_code == 401

    def test_verify_malformed_token(self):
        """Test that malformed tokens are rejected."""
        with pytest.raises(Exception) as exc_info:
            verify_token("not-a-valid-jwt", TEST_JWT_CONFIG)

        assert exc_info.value.status_code == 401


class TestExtractTokenFromHeader:
    """Tests for token extraction from Authorization header."""

    def test_extract_valid_bearer_token(self):
        """Test extracting token from valid Bearer header."""
        token = extract_token_from_header("Bearer abc123xyz")
        assert token == "abc123xyz"

    def test_extract_missing_header(self):
        """Test that missing header raises error."""
        with pytest.raises(Exception) as exc_info:
            extract_token_from_header(None)

        assert exc_info.value.status_code == 401
        assert "Missing Authorization header" in str(exc_info.value.detail)

    def test_extract_invalid_format(self):
        """Test that invalid header format raises error."""
        with pytest.raises(Exception) as exc_info:
            extract_token_from_header("InvalidFormat abc123")

        assert exc_info.value.status_code == 401
        assert "Invalid Authorization header format" in str(exc_info.value.detail)

    def test_extract_missing_token(self):
        """Test that missing token raises error."""
        with pytest.raises(Exception) as exc_info:
            extract_token_from_header("Bearer")

        assert exc_info.value.status_code == 401


class TestJWTAuthenticationMiddleware:
    """Tests for JWT authentication middleware."""

    def test_access_public_endpoint_without_token(self, client):
        """Test accessing public endpoint without authentication."""
        response = client.get("/public")
        assert response.status_code == 200
        assert response.json() == {"message": "public"}

    def test_access_protected_endpoint_without_token(self, client):
        """Test accessing protected endpoint without token fails."""
        response = client.get("/protected")
        assert response.status_code == 401

    def test_access_protected_endpoint_with_valid_token(self, client, valid_token):
        """Test accessing protected endpoint with valid token."""
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "protected"
        assert data["user_id"] == "user-123"
        assert data["username"] == "test@example.com"

    def test_access_with_invalid_token(self, client):
        """Test that invalid token is rejected."""
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    def test_preflight_options_request(self, client):
        """Test that OPTIONS preflight requests bypass auth."""
        response = client.options("/protected")
        # Should not require authentication
        assert response.status_code in [200, 405]  # 405 if no OPTIONS handler


class TestRoleBasedAccess:
    """Tests for role-based access control."""

    def test_access_admin_endpoint_with_admin_role(self, client, admin_token):
        """Test admin can access admin endpoint."""
        response = client.get(
            "/admin",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "admin"

    def test_access_admin_endpoint_without_admin_role(self, client, valid_token):
        """Test non-admin cannot access admin endpoint."""
        response = client.get(
            "/admin",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 403
        assert "Insufficient permissions" in str(response.json())


class TestPermissionBasedAccess:
    """Tests for permission-based access control."""

    def test_access_with_required_permission(self, client, admin_token):
        """Test access with required permission."""
        response = client.get(
            "/with-permission",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "permission"

    def test_access_without_required_permission(self, client, valid_token):
        """Test access denied without required permission."""
        response = client.get(
            "/with-permission",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 403


class TestUserIdentity:
    """Tests for UserIdentity model."""

    def test_user_identity_creation(self):
        """Test creating UserIdentity."""
        identity = UserIdentity(
            user_id="user-123",
            username="test@example.com",
            organization_id="org-456",
            roles=["admin"],
            permissions=["slo:write"],
        )

        assert identity.user_id == "user-123"
        assert identity.username == "test@example.com"
        assert identity.organization_id == "org-456"
        assert identity.roles == ["admin"]
        assert identity.permissions == ["slo:write"]

    def test_user_identity_immutable(self):
        """Test that UserIdentity is immutable."""
        identity = UserIdentity(
            user_id="user-123",
            username="test@example.com",
        )

        with pytest.raises(Exception):
            identity.user_id = "different-user"
