"""Tests for the MCP server layer."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import pytest
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    CallToolResult,
    ListToolsRequest,
    TextContent,
)

from backend2mcp.core.auth import AuthContext, AuthProvider
from backend2mcp.core.server import MCPServer
from backend2mcp.core.simple import SimpleAdapter
from backend2mcp.core.tool import mcp_tool


async def echo(*, value: str = "hi") -> dict[str, str]:
    return {"echo": value}


@mcp_tool(hidden=True)
def hidden() -> str:
    return "hidden"


@mcp_tool(required_permissions=["admin"])
def admin_only() -> str:
    return "secret"


class FakeAdapter(SimpleAdapter):
    def __init__(self, auth_provider: AuthProvider | None = None):
        super().__init__(app=object(), auth_provider=auth_provider)

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        return [
            ("/echo/{value}", "GET", echo, None),
            ("/hidden", "GET", hidden, None),
            ("/admin", "GET", admin_only, None),
        ]


class AdminProvider(AuthProvider):
    def get_auth_context(self, request: Any) -> AuthContext:
        return AuthContext(permissions={"admin"})


@pytest.fixture
def server() -> MCPServer:
    return MCPServer(FakeAdapter(), "test-server")


def test_tool_infos(server: MCPServer):
    infos = server._get_tool_infos()
    assert [info.name for info in infos] == ["get_by_value", "get_hidden", "get_admin"]


def test_list_tools_hides_hidden(server: MCPServer):
    result = asyncio.run(
        server._server.request_handlers[ListToolsRequest](ListToolsRequest())
    )
    tools = result.root.tools
    names = [tool.name for tool in tools]
    assert "get_by_value" in names
    assert "get_hidden" not in names


def _call(server: MCPServer, name: str, arguments: dict[str, Any] | None = None) -> CallToolResult:
    request = CallToolRequest(
        params=CallToolRequestParams(name=name, arguments=arguments or {})
    )
    result = asyncio.run(server._server.request_handlers[CallToolRequest](request))
    return result.root


def test_call_async_tool(server: MCPServer):
    result = _call(server, "get_by_value", {"value": "hello"})
    assert result.isError is False
    assert isinstance(result.content[0], TextContent)
    assert "hello" in result.content[0].text


def test_call_unknown_tool(server: MCPServer):
    result = _call(server, "missing")
    assert result.isError is True
    assert "not found" in result.content[0].text


def test_permission_enforcement():
    from backend2mcp.core.auth import NoAuthProvider

    server = MCPServer(FakeAdapter(NoAuthProvider()), "test-server")
    denied = _call(server, "get_admin")
    assert denied.isError is True
    assert "Permission denied" in denied.content[0].text


def test_admin_allowed():
    server = MCPServer(FakeAdapter(AdminProvider()), "test-server")
    result = _call(server, "get_admin")
    assert result.isError is False
    assert "secret" in result.content[0].text
