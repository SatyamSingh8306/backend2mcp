"""backend2mcp.core - Core abstractions and shared implementation."""

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.auth import (
    APIKeyAuthProvider,
    AuthContext,
    AuthProvider,
    BearerAuthProvider,
    HeaderInjectionAuthProvider,
    NoAuthProvider,
    combine_providers,
)
from backend2mcp.core.exceptions import (
    AdapterConfigurationError,
    AuthenticationError,
    Backend2MCPError,
    RouteIntrospectionError,
    SchemaConversionError,
    ToolExecutionError,
)
from backend2mcp.core.schema import (
    extract_schema_from_signature,
    route_to_description,
    schema_from_path,
    type_to_json_schema,
)
from backend2mcp.core.server import MCPServer
from backend2mcp.core.tool import build_tool_name, mcp_tool, normalize_route_path

__all__ = [
    "BaseAdapter",
    "ToolInfo",
    "MCPServer",
    # Tools / schemas
    "mcp_tool",
    "build_tool_name",
    "normalize_route_path",
    "type_to_json_schema",
    "extract_schema_from_signature",
    "schema_from_path",
    "route_to_description",
    # Auth
    "AuthContext",
    "AuthProvider",
    "NoAuthProvider",
    "BearerAuthProvider",
    "APIKeyAuthProvider",
    "HeaderInjectionAuthProvider",
    "combine_providers",
    # Exceptions
    "Backend2MCPError",
    "AdapterConfigurationError",
    "AuthenticationError",
    "RouteIntrospectionError",
    "SchemaConversionError",
    "ToolExecutionError",
]
