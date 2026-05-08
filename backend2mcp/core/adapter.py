"""Abstract base adapter and tool info structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, Field


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
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a tool by calling its handler with resolved arguments.

        Args:
            handler: The route handler function
            arguments: Resolved arguments from MCP request
            context: Optional auth/context dict

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