"""MCP Server implementation using the official SDK.

The low-level ``Server`` API changed in MCP Python SDK 2.0: the
``@server.list_tools()`` / ``@server.call_tool()`` decorators were replaced by
``on_list_tools=`` / ``on_call_tool=`` constructor parameters whose handlers
take ``(ctx, params)`` and return fully-built result objects.  Both shapes are
supported here so backend2mcp runs with mcp 1.x and 2.x without a hard pin.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool as MCPTool

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.utils import serialize_result

# v2 removed the decorator methods from the low-level Server class.
_MCP_SDK_V2 = not hasattr(Server, "list_tools")


class MCPServer:
    """Coordinate a framework adapter with the MCP stdio transport."""

    def __init__(
        self,
        adapter: BaseAdapter,
        name: str = "backend2mcp",
        cache_tools: bool = True,
    ):
        self.adapter = adapter
        self.name = name
        self.cache_tools = cache_tools
        self._tool_cache: list[ToolInfo] | None = None
        if _MCP_SDK_V2:
            # SDK >= 2.0: handlers are constructor parameters.
            self._server = Server(
                name,
                on_list_tools=self._list_tools_v2,
                on_call_tool=self._call_tool_v2,
            )
        else:
            # SDK 1.x: handlers are registered through decorators.
            self._server = Server(name)
            self._setup_handlers_v1()

    def refresh_tools(self) -> None:
        """Discard cached tool metadata so routes are re-introspected."""
        self._tool_cache = None

    def _get_tool_infos(self) -> list[ToolInfo]:
        """Introspect all routes, de-duplicating tool names."""
        if self.cache_tools and self._tool_cache is not None:
            return self._tool_cache

        infos: list[ToolInfo] = []
        seen: set[str] = set()
        for path, method, handler, config in self.adapter.get_routes():
            try:
                info = self.adapter.introspect_route(path, method, handler, config)
            except Exception:
                # A single malformed route must not take down the whole server.
                continue
            if info.name in seen:
                continue
            seen.add(info.name)
            infos.append(info)

        if self.cache_tools:
            self._tool_cache = infos
        return infos

    def _build_tools(self) -> list[MCPTool]:
        """Build the MCP tool definitions for all visible routes."""
        return [MCPTool(**info.to_mcp_tool()) for info in self._get_tool_infos() if not info.hidden]

    @staticmethod
    def _error_result(message: str) -> CallToolResult:
        # ``isError`` is the wire key in both SDK majors; validate from a dict
        # so the constructor keyword rename in v2 does not matter here.
        return CallToolResult.model_validate(
            {"content": [TextContent(type="text", text=message)], "isError": True}
        )

    async def _dispatch_call(self, name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        """Resolve, authorize and execute a tool call (shared by both SDKs)."""
        info = next(
            (item for item in self._get_tool_infos() if item.name == name and not item.hidden),
            None,
        )
        if info is None:
            return self._error_result(f"Tool not found: {name}")

        auth_context = self.adapter.get_auth_context()
        if info.required_permissions and not self.adapter.auth_provider.validate_request(
            auth_context, info.required_permissions
        ):
            return self._error_result(
                f"Permission denied for tool '{name}'. "
                f"Required: {', '.join(info.required_permissions)}"
            )

        try:
            # Off-load synchronous/blocking handlers so the MCP event loop
            # stays responsive; async handlers still work because
            # adapters use ``run_coroutine_sync`` internally.
            result = await asyncio.to_thread(
                self.adapter.execute_tool,
                info.handler,
                arguments or {},
                auth_context,
            )
            return CallToolResult(content=[TextContent(type="text", text=serialize_result(result))])
        except Exception as exc:
            return self._error_result(f"Error executing tool '{name}': {exc}")

    # -- MCP SDK 1.x: decorator-based handlers -------------------------------

    def _setup_handlers_v1(self) -> None:
        @self._server.list_tools()  # type: ignore[untyped-decorator]
        async def list_tools() -> list[MCPTool]:
            """Return all visible tools derived from the adapter's routes."""
            return self._build_tools()

        @self._server.call_tool()  # type: ignore[untyped-decorator]
        async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
            """Execute a tool by name and return MCP content blocks.

            Return bare content blocks rather than a CallToolResult: early mcp
            1.x decorators wrap the return value unconditionally, while later
            ones pass a CallToolResult through. Raise on errors so every v1
            decorator builds the isError result itself.
            """
            result = await self._dispatch_call(name, arguments)
            if result.model_dump(by_alias=True).get("isError"):
                raise RuntimeError(result.content[0].text)
            return result.content

    # -- MCP SDK 2.x: constructor-based handlers -----------------------------

    async def _list_tools_v2(self, ctx: Any, params: Any) -> ListToolsResult:
        """Return all visible tools derived from the adapter's routes."""
        return ListToolsResult(tools=self._build_tools())

    async def _call_tool_v2(self, ctx: Any, params: Any) -> CallToolResult:
        """Execute a tool by name and return MCP content blocks."""
        return await self._dispatch_call(params.name, params.arguments or {})

    async def run(self) -> None:
        """Run the MCP server using stdio transport."""
        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(
                read_stream,
                write_stream,
                self._server.create_initialization_options(),
            )

    def run_sync(self) -> None:
        """Run the server synchronously (blocking)."""
        asyncio.run(self.run())
