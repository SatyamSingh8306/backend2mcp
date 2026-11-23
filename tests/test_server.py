"""Tests for the MCP server layer."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import pytest
from mcp.server import Server
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    TextContent,
)

from backend2mcp.core.auth import AuthContext, AuthProvider
from backend2mcp.core.server import MCPServer
from backend2mcp.core.simple import SimpleAdapter
from backend2mcp.core.tool import mcp_tool

# MCP SDK v2 dropped the low-level ``request_handlers`` dict in favour of
# ``get_request_handler(method)`` entries invoked with ``(ctx, params)``.
_MCP_SDK_V2 = not hasattr(Server, "list_tools")


def _is_error(result: CallToolResult) -> bool:
    """Read the error flag across SDKs (renamed ``isError`` -> ``is_error`` in v2)."""
    return bool(getattr(result, "is_error", None) or getattr(result, "isError", False))


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


def _list_tools(server: MCPServer) -> ListToolsResult:
    """Invoke the registered tools/list handler on either MCP SDK major."""
    if _MCP_SDK_V2:
        entry = server._server.get_request_handler("tools/list")
        assert entry is not None
        return asyncio.run(entry.handler(None, entry.params_type()))
    result = asyncio.run(
        server._server.request_handlers[ListToolsRequest](ListToolsRequest(method="tools/list"))
    )
    return result.root


def test_list_tools_hides_hidden(server: MCPServer):
    tools = _list_tools(server).tools
    names = [tool.name for tool in tools]
    assert "get_by_value" in names
    assert "get_hidden" not in names


def _call(server: MCPServer, name: str, arguments: dict[str, Any] | None = None) -> CallToolResult:
    if _MCP_SDK_V2:
        entry = server._server.get_request_handler("tools/call")
        assert entry is not None
        params = entry.params_type(name=name, arguments=arguments or {})
        return asyncio.run(entry.handler(None, params))
    request = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name=name, arguments=arguments or {}),
    )
    result = asyncio.run(server._server.request_handlers[CallToolRequest](request))
    return result.root


def test_call_async_tool(server: MCPServer):
    result = _call(server, "get_by_value", {"value": "hello"})
    assert _is_error(result) is False
    assert isinstance(result.content[0], TextContent)
    assert "hello" in result.content[0].text


def test_call_unknown_tool(server: MCPServer):
    result = _call(server, "missing")
    assert _is_error(result) is True
    assert "not found" in result.content[0].text


def test_permission_enforcement():
    from backend2mcp.core.auth import NoAuthProvider

    server = MCPServer(FakeAdapter(NoAuthProvider()), "test-server")
    denied = _call(server, "get_admin")
    assert _is_error(denied) is True
    assert "Permission denied" in denied.content[0].text


def test_admin_allowed():
    server = MCPServer(FakeAdapter(AdminProvider()), "test-server")
    result = _call(server, "get_admin")
    assert _is_error(result) is False
    assert "secret" in result.content[0].text


def test_registration_strategy_matches_installed_sdk(server: MCPServer):
    if _MCP_SDK_V2:
        assert server._server.get_request_handler("tools/list") is not None
        assert server._server.get_request_handler("tools/call") is not None
    else:
        assert ListToolsRequest in server._server.request_handlers
        assert CallToolRequest in server._server.request_handlers


def test_v2_handlers_work_under_either_sdk(server: MCPServer):
    """The v2 handler shape must stay functional even when tests run on SDK 1.x."""
    listed = asyncio.run(server._list_tools_v2(None, None))
    names = [tool.name for tool in listed.tools]
    assert "get_by_value" in names
    assert "get_hidden" not in names

    class Params:
        name = "get_by_value"
        arguments = {"value": "from-v2-handler"}

    called = asyncio.run(server._call_tool_v2(None, Params()))
    assert _is_error(called) is False
    assert "from-v2-handler" in called.content[0].text
