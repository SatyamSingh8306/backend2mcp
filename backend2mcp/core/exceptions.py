"""Structured exceptions for backend2mcp."""


class Backend2MCPError(Exception):
    """Base exception for all backend2mcp errors."""

    pass


class RouteIntrospectionError(Backend2MCPError):
    """Raised when route introspection fails."""

    pass


class SchemaConversionError(Backend2MCPError):
    """Raised when converting route schemas to MCP format fails."""

    pass


class ToolExecutionError(Backend2MCPError):
    """Raised when executing a tool fails."""

    pass


class AdapterConfigurationError(Backend2MCPError):
    """Raised when adapter is misconfigured."""

    pass


class AuthenticationError(Backend2MCPError):
    """Raised when a tool call is not allowed by the configured auth provider."""

    pass