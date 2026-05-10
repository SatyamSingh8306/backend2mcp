"""backend2mcp.core - Core abstractions and shared implementation."""

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.auth import (
    AuthContext,
    AuthProvider,
    APIKeyAuthProvider,
    BearerAuthProvider,
    HeaderInjectionAuthProvider,
    NoAuthProvider,
    combine_providers,
)
from backend2mcp.core.exceptions import (
    AdapterConfigurationError,
    RouteIntrospectionError,
    SchemaConversionError,
    ToolExecutionError,
)
from backend2mcp.core.server import MCPServer

__all__ = [
    "BaseAdapter",
    "ToolInfo",
    "MCPServer",
    # Auth
    "AuthContext",
    "AuthProvider",
    "NoAuthProvider",
    "BearerAuthProvider",
    "APIKeyAuthProvider",
    "HeaderInjectionAuthProvider",
    "combine_providers",
    # Exceptions
    "AdapterConfigurationError",
    "RouteIntrospectionError",
    "SchemaConversionError",
    "ToolExecutionError",
]