"""Tests for auth module."""

import pytest

from backend2mcp.core.auth import (
    APIKeyAuthProvider,
    AuthContext,
    AuthProvider,
    BearerAuthProvider,
    HeaderInjectionAuthProvider,
    NoAuthProvider,
    combine_providers,
)


class TestAuthContext:
    """Test AuthContext dataclass."""

    def test_default_context(self):
        """Test default values."""
        ctx = AuthContext()
        assert ctx.headers == {}
        assert ctx.user_id is None
        assert ctx.permissions == set()
        assert ctx.token is None
        assert ctx.extra == {}

    def test_custom_context(self):
        """Test custom values."""
        ctx = AuthContext(
            headers={"Authorization": "Bearer xyz"},
            user_id="user123",
            permissions={"read", "write"},
            token="xyz",
            extra={"role": "admin"},
        )
        assert ctx.headers["Authorization"] == "Bearer xyz"
        assert ctx.user_id == "user123"
        assert "read" in ctx.permissions
        assert "write" in ctx.permissions
        assert ctx.token == "xyz"
        assert ctx.extra["role"] == "admin"

    def test_has_permission(self):
        """Test permission checking."""
        ctx = AuthContext(permissions={"read", "write"})
        assert ctx.has_permission("read") is True
        assert ctx.has_permission("write") is True
        assert ctx.has_permission("admin") is False


class TestNoAuthProvider:
    """Test NoAuthProvider."""

    def test_returns_empty_context(self):
        """Test that NoAuthProvider always returns empty context."""
        provider = NoAuthProvider()
        ctx = provider.get_auth_context({})
        assert isinstance(ctx, AuthContext)
        assert ctx.headers == {}
        assert ctx.user_id is None


class TestBearerAuthProvider:
    """Test BearerAuthProvider."""

    def test_valid_bearer_token(self):
        """Test extracting valid bearer token from headers."""
        provider = BearerAuthProvider()
        mock_request = type("Request", (), {"headers": {"Authorization": "Bearer mytoken123"}})

        ctx = provider.get_auth_context(mock_request)
        assert ctx.token == "mytoken123"
        assert ctx.user_id is not None
        assert "default" in ctx.permissions

    def test_no_bearer_prefix(self):
        """Test when authorization header doesn't have Bearer prefix."""
        provider = BearerAuthProvider()
        mock_request = type("Request", (), {"headers": {"Authorization": "Basic abc"}})

        ctx = provider.get_auth_context(mock_request)
        assert ctx.token is None
        assert ctx.user_id is None

    def test_valid_tokens_whitelist(self):
        """Test token validation with whitelist."""
        provider = BearerAuthProvider(validate_tokens=["valid-token", "another-token"])
        mock_request = type("Request", (), {"headers": {"Authorization": "Bearer valid-token"}})

        ctx = provider.get_auth_context(mock_request)
        assert ctx.token == "valid-token"

    def test_invalid_token_whitelist(self):
        """Test rejection of invalid token in whitelist mode."""
        provider = BearerAuthProvider(validate_tokens=["valid-token"])
        mock_request = type("Request", (), {"headers": {"Authorization": "Bearer invalid-token"}})

        ctx = provider.get_auth_context(mock_request)
        assert ctx.token is None
        assert ctx.user_id is None

    def test_custom_header(self):
        """Test custom header name."""
        provider = BearerAuthProvider(token_header="X-Auth-Token")
        mock_request = type("Request", (), {"headers": {"X-Auth-Token": "Bearer custom"}})

        ctx = provider.get_auth_context(mock_request)
        assert ctx.token == "custom"

    def test_flask_request_extraction(self):
        """Test extraction from Flask-style request."""
        provider = BearerAuthProvider()
        # Flask stores headers in HTTP_ prefixed environ keys
        mock_request = type("Request", (), {
            "environ": {
                "HTTP_AUTHORIZATION": "Bearer flask-token"
            }
        })

        ctx = provider.get_auth_context(mock_request)
        assert ctx.token == "flask-token"

    def test_django_request_extraction(self):
        """Test extraction from Django-style request."""
        provider = BearerAuthProvider()
        # Django stores headers in META dict
        mock_request = type("Request", (), {
            "META": {
                "HTTP_AUTHORIZATION": "Bearer django-token"
            }
        })

        ctx = provider.get_auth_context(mock_request)
        assert ctx.token == "django-token"


class TestAPIKeyAuthProvider:
    """Test APIKeyAuthProvider."""

    def test_api_key_from_header(self):
        """Test extracting API key from header."""
        provider = APIKeyAuthProvider(header_name="X-API-Key")
        mock_request = type("Request", (), {"headers": {"X-API-Key": "api-key-123"}})

        ctx = provider.get_auth_context(mock_request)
        assert ctx.token == "api-key-123"
        assert "api" in ctx.permissions

    def test_api_key_from_query(self):
        """Test extracting API key from query param."""
        provider = APIKeyAuthProvider(query_param="api_key")

        class MockRequest:
            headers = {}
            query_params = {"api_key": "query-key-456"}

        ctx = provider.get_auth_context(MockRequest())
        assert ctx.token == "query-key-456"

    def test_valid_keys_whitelist(self):
        """Test API key validation with whitelist."""
        provider = APIKeyAuthProvider(valid_keys=["key1", "key2"])
        mock_request = type("Request", (), {"headers": {"X-API-Key": "key1"}})

        ctx = provider.get_auth_context(mock_request)
        assert ctx.token == "key1"

    def test_invalid_key_rejected(self):
        """Test rejection of invalid API key."""
        provider = APIKeyAuthProvider(valid_keys=["key1"])
        mock_request = type("Request", (), {"headers": {"X-API-Key": "invalid"}})

        ctx = provider.get_auth_context(mock_request)
        assert ctx.token is None


class TestHeaderInjectionAuthProvider:
    """Test HeaderInjectionAuthProvider."""

    def test_inject_static_headers(self):
        """Test injection of static headers."""
        provider = HeaderInjectionAuthProvider(
            static_headers={"X-Custom-Header": "static-value", "Authorization": "Bearer injected"}
        )
        mock_request = type("Request", (), {"headers": {"X-Other-Header": "other"}})

        ctx = provider.get_auth_context(mock_request)
        assert ctx.headers["X-Custom-Header"] == "static-value"
        assert ctx.headers["Authorization"] == "Bearer injected"
        # Original header preserved if not overridden
        assert ctx.headers.get("X-Other-Header") == "other"

    def test_static_headers_override_request(self):
        """Test that static headers override request headers."""
        provider = HeaderInjectionAuthProvider(
            static_headers={"X-Header": "static"}
        )
        mock_request = type("Request", (), {"headers": {"X-Header": "original"}})

        ctx = provider.get_auth_context(mock_request)
        assert ctx.headers["X-Header"] == "static"


class TestCombineProviders:
    """Test combine_providers function."""

    def test_first_valid_wins(self):
        """Test that first provider with valid auth wins."""
        no_auth = NoAuthProvider()

        def custom_get_context(request):
            return AuthContext(user_id="custom")

        class CustomProvider(AuthProvider):
            def get_auth_context(self, request):
                return custom_get_context(request)

        combined = combine_providers(no_auth, CustomProvider())
        ctx = combined.get_auth_context({})
        assert ctx.user_id == "custom"

    def test_all_empty_returns_empty(self):
        """Test when all providers return empty context."""
        combined = combine_providers(NoAuthProvider(), NoAuthProvider())
        ctx = combined.get_auth_context({})
        assert ctx.user_id is None


class TestAuthProviderBase:
    """Test base AuthProvider class."""

    def test_validate_request_all_permissions(self):
        """Test validation with all required permissions."""
        provider = NoAuthProvider()
        ctx = AuthContext(permissions={"read", "write"})

        assert provider.validate_request(ctx, ["read"]) is True
        assert provider.validate_request(ctx, ["read", "write"]) is True

    def test_validate_request_missing_permission(self):
        """Test validation fails for missing permissions."""
        provider = NoAuthProvider()
        ctx = AuthContext(permissions={"read"})

        assert provider.validate_request(ctx, ["read", "admin"]) is False