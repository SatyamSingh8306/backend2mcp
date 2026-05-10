"""Authentication providers for backend2mcp."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


@dataclass
class AuthContext:
    """Authentication context passed to tool execution.

    Attributes:
        headers: Headers to include in requests/handler calls
        user_id: Authenticated user ID (if authenticated)
        permissions: Set of permission strings
        token: The bearer token (if applicable)
        extra: Additional custom auth data
    """
    headers: dict[str, str] = field(default_factory=dict)
    user_id: str | None = None
    permissions: set[str] = field(default_factory=set)
    token: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: str) -> bool:
        """Check if context has a specific permission."""
        return permission in self.permissions


class AuthProvider(ABC):
    """Abstract base class for authentication providers.

    Implement this to add custom auth behavior for your framework.
    """

    @abstractmethod
    def get_auth_context(self, request: Any) -> AuthContext:
        """Extract auth context from an incoming request.

        Args:
            request: Framework-specific request object

        Returns:
            AuthContext with extracted auth data
        """
        pass

    def validate_request(self, context: AuthContext, required_permissions: list[str]) -> bool:
        """Validate that request has required permissions.

        Override this for custom validation logic.

        Args:
            context: AuthContext from get_auth_context
            required_permissions: List of permission strings

        Returns:
            True if request is valid, False otherwise
        """
        return all(context.has_permission(p) for p in required_permissions)


class NoAuthProvider(AuthProvider):
    """Default provider - no authentication required."""

    def get_auth_context(self, request: Any) -> AuthContext:
        """Return empty auth context (no auth)."""
        return AuthContext()


class BearerAuthProvider(AuthProvider):
    """Bearer token authentication provider.

    Extracts and validates Bearer tokens from Authorization header.
    """

    def __init__(
        self,
        token_header: str = "Authorization",
        token_prefix: str = "Bearer",
        validate_tokens: list[str] | None = None,
    ):
        """Initialize the provider.

        Args:
            token_header: Header name for token (default: Authorization)
            token_prefix: Prefix before token (default: Bearer)
            validate_tokens: List of valid tokens (empty = accept any)
        """
        self.token_header = token_header
        self.token_prefix = token_prefix
        self.valid_tokens = set(validate_tokens or [])

    def get_auth_context(self, request: Any) -> AuthContext:
        """Extract bearer token from request headers."""
        # Try to get header from various framework request objects
        headers = self._extract_headers(request)

        auth_header = headers.get(self.token_header, "")

        if not auth_header.startswith(f"{self.token_prefix} "):
            return AuthContext()

        token = auth_header[len(self.token_prefix) + 1 :]

        # Validate if we have a token whitelist
        if self.valid_tokens and token not in self.valid_tokens:
            return AuthContext()

        return AuthContext(
            headers=headers,
            token=token,
            user_id=token[:8] if token else None,  # Use token prefix as user ID
            permissions={"default"},
        )

    def _extract_headers(self, request: Any) -> dict[str, str]:
        """Extract headers from framework-specific request."""
        # FastAPI/Starlette
        if hasattr(request, "headers"):
            return dict(request.headers)

        # Flask
        if hasattr(request, "environ"):
            headers = {}
            for key, value in request.environ.items():
                if key.startswith("HTTP_"):
                    header_name = key[5:].replace("_", "-").title()
                    headers[header_name] = value
            return headers

        # Django
        if hasattr(request, "META"):
            headers = {}
            for key, value in request.META.items():
                if key.startswith("HTTP_"):
                    header_name = key[5:].replace("_", "-").title()
                    headers[header_name] = value
            return headers

        return {}


class APIKeyAuthProvider(AuthProvider):
    """API Key authentication provider.

    Extracts API key from query parameter or header.
    """

    def __init__(
        self,
        header_name: str = "X-API-Key",
        query_param: str = "api_key",
        valid_keys: list[str] | None = None,
    ):
        """Initialize the provider.

        Args:
            header_name: Header name for API key
            query_param: Query parameter name for API key
            valid_keys: List of valid API keys (empty = accept any)
        """
        self.header_name = header_name
        self.query_param = query_param
        self.valid_keys = set(valid_keys or [])

    def get_auth_context(self, request: Any) -> AuthContext:
        """Extract API key from header or query param."""
        # FastAPI/Starlette
        if hasattr(request, "headers"):
            headers = dict(request.headers)
            api_key = headers.get(self.header_name) or request.query_params.get(self.query_param)
        # Flask
        elif hasattr(request, "environ"):
            headers = {self.header_name: request.environ.get(f"HTTP_{self.header_name.upper().replace('-', '_')}", "")}
            api_key = headers.get(self.header_name) or request.args.get(self.query_param)
        # Django
        elif hasattr(request, "META"):
            headers = {self.header_name: request.META.get(f"HTTP_{self.header_name.upper().replace('-', '_')}", "")}
            api_key = headers.get(self.header_name) or request.GET.get(self.query_param)
        else:
            return AuthContext()

        if not api_key:
            return AuthContext()

        if self.valid_keys and api_key not in self.valid_keys:
            return AuthContext()

        return AuthContext(
            headers=headers,
            user_id=f"apikey-{api_key[:8]}",
            permissions={"api"},
        )


class HeaderInjectionAuthProvider(AuthProvider):
    """Always injects custom headers into auth context.

    Useful for forwarding headers to downstream services.
    """

    def __init__(self, static_headers: dict[str, str]):
        """Initialize with static headers to inject.

        Args:
            static_headers: Headers to inject into every request
        """
        self.static_headers = static_headers

    def get_auth_context(self, request: Any) -> AuthContext:
        """Return context with injected headers."""
        # Extract request headers
        if hasattr(request, "headers"):
            request_headers = dict(request.headers)
        elif hasattr(request, "environ"):
            request_headers = {}
            for key, value in request.environ.items():
                if key.startswith("HTTP_"):
                    header_name = key[5:].replace("_", "-").title()
                    request_headers[header_name] = value
        else:
            request_headers = {}

        # Merge static headers (static take precedence)
        merged_headers = {**request_headers, **self.static_headers}

        return AuthContext(
            headers=merged_headers,
            permissions={"default"},
        )


def combine_providers(*providers: AuthProvider) -> AuthProvider:
    """Combine multiple auth providers (first valid match wins).

    Returns a provider that tries each provider in order.
    """
    combined = _CombinedAuthProvider(providers)
    return combined


class _CombinedAuthProvider(AuthProvider):
    """Auth provider that combines multiple providers."""

    def __init__(self, providers: tuple[AuthProvider, ...]):
        self.providers = providers

    def get_auth_context(self, request: Any) -> AuthContext:
        """Try each provider, return first non-empty context."""
        for provider in self.providers:
            context = provider.get_auth_context(request)
            if context.token or context.user_id or context.permissions:
                return context
        return AuthContext()