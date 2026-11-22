"""MCP Server implementation using the official SDK."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool as MCPTool

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.utils import serialize_result


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
        self._server = Server(name)
        self._setup_handlers()

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

    @staticmethod
    def _error_result(message: str) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text=message)],
            isError=True,
        )

    def _setup_handlers(self) -> None:
        """Register MCP request handlers."""

        @self._server.list_tools()  # type: ignore[untyped-decorator]
        async def list_tools() -> list[MCPTool]:
            """Return all visible tools derived from the adapter's routes."""
            return [
                MCPTool(**info.to_mcp_tool())
                for info in self._get_tool_infos()
                if not info.hidden
            ]

        @self._server.call_tool()  # type: ignore[untyped-decorator]
        async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
            """Execute a tool by name and return MCP content blocks."""
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
                return [TextContent(type="text", text=serialize_result(result))]
            except Exception as exc:
                return self._error_result(f"Error executing tool '{name}': {exc}")

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
