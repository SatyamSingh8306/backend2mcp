"""Abstract base adapter and tool info structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from backend2mcp.core.auth import AuthContext, AuthProvider, NoAuthProvider


@dataclass
class ToolInfo:
    """Information about an MCP tool derived from a route."""

    name: str
    description: str
    route_path: str
    http_method: str
    handler: Callable[..., Any]
    input_schema: dict[str, Any]
    hidden: bool = False
    required_permissions: list[str] = field(default_factory=list)

    def to_mcp_tool(self) -> dict[str, Any]:
        """Convert to MCP tool specification."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                **self.input_schema,
            },
        }


class BaseAdapter(ABC):
    """Abstract base class for framework-specific MCP adapters.

    All framework adapters must implement these methods.
    """

    def __init__(
        self,
        auth_provider: AuthProvider | None = None,
    ):
        """Initialize the adapter with optional auth provider.

        Args:
            auth_provider: Optional auth provider. Defaults to NoAuthProvider.
        """
        self._auth_provider = auth_provider or NoAuthProvider()

    @property
    def auth_provider(self) -> AuthProvider:
        """Get the auth provider."""
        return self._auth_provider

    @auth_provider.setter
    def auth_provider(self, provider: AuthProvider) -> None:
        """Set a custom auth provider."""
        self._auth_provider = provider

    def get_auth_context(self, request: Any = None) -> AuthContext:
        """Get auth context from request using the auth provider.

        Args:
            request: Framework-specific request object (optional)

        Returns:
            AuthContext with auth information
        """
        return self._auth_provider.get_auth_context(request or {})

    @abstractmethod
    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], dict[str, Any]]]:
        """Get all routes from the framework app.

        Returns:
            List of tuples: (path, http_method, handler, raw_config)
        """
        pass

    @abstractmethod
    def introspect_route(
        self, path: str, method: str, handler: Callable[..., Any], config: Any
    ) -> ToolInfo:
        """Introspect a single route and return tool information.

        Args:
            path: The route path (e.g., "/users/{id}")
            method: HTTP method (GET, POST, etc.)
            handler: The route handler function
            config: Framework-specific route configuration

        Returns:
            ToolInfo with name, description, and input_schema
        """
        pass

    @abstractmethod
    def execute_tool(
        self,
        handler: Callable[..., Any],
        arguments: dict[str, Any],
        auth_context: AuthContext | None = None,
    ) -> Any:
        """Execute a tool by calling its handler with resolved arguments.

        Args:
            handler: The route handler function
            arguments: Resolved arguments from MCP request
            auth_context: AuthContext with auth information

        Returns:
            The handler's return value, serialized appropriately
        """
        pass

    @abstractmethod
    def get_app(self) -> Any:
        """Get the underlying framework application object."""
        pass

    @abstractmethod
    def build_tool_name(self, http_method: str, path: str) -> str:
        """Build a deterministic, MCP-safe tool name from method and path.

        Args:
            http_method: HTTP method (GET, POST, etc.)
            path: Route path

        Returns:
            Sanitized tool name (alphanumeric + underscores)
        """
        pass