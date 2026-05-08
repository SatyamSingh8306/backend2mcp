"""Tests for core module."""

import pytest

from backend2mcp.core.exceptions import (
    AdapterConfigurationError,
    Backend2MCPError,
    RouteIntrospectionError,
    SchemaConversionError,
    ToolExecutionError,
)


class TestExceptions:
    """Test exception hierarchy and messages."""

    def test_backend2mcp_error_is_base(self):
        """Test that all custom exceptions inherit from base."""
        assert issubclass(AdapterConfigurationError, Backend2MCPError)
        assert issubclass(RouteIntrospectionError, Backend2MCPError)
        assert issubclass(SchemaConversionError, Backend2MCPError)
        assert issubclass(ToolExecutionError, Backend2MCPError)

    def test_exception_messages(self):
        """Test exception messages are descriptive."""
        with pytest.raises(AdapterConfigurationError) as exc_info:
            raise AdapterConfigurationError("Test message")
        assert "Test message" in str(exc_info.value)

        with pytest.raises(RouteIntrospectionError) as exc_info:
            raise RouteIntrospectionError("Route introspection failed")
        assert "Route introspection failed" in str(exc_info.value)

        with pytest.raises(SchemaConversionError) as exc_info:
            raise SchemaConversionError("Schema conversion failed")
        assert "Schema conversion failed" in str(exc_info.value)

        with pytest.raises(ToolExecutionError) as exc_info:
            raise ToolExecutionError("Tool execution failed")
        assert "Tool execution failed" in str(exc_info.value)

    def test_exception_can_be_caught_as_base(self):
        """Test that specific exceptions can be caught as base exception."""
        with pytest.raises(Backend2MCPError):
            raise RouteIntrospectionError("test")

        with pytest.raises(Backend2MCPError):
            raise SchemaConversionError("test")

        with pytest.raises(Backend2MCPError):
            raise ToolExecutionError("test")

        with pytest.raises(Backend2MCPError):
            raise AdapterConfigurationError("test")