"""MCP Server implementation using the official SDK."""

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool as MCPTool

from backend2mcp.core.adapter import BaseAdapter


class MCPServer:
    """MCP Server wrapper that coordinates adapter and transport."""

    def __init__(self, adapter: BaseAdapter, name: str = "backend2mcp"):
        self.adapter = adapter
        self.name = name
        self._server = Server(name)
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Register MCP request handlers."""

        @self._server.list_tools()
        async def list_tools() -> list[MCPTool]:
            """Return all available tools from the adapter."""
            tools = []
            for route in self.adapter.get_routes():
                path, method, handler, config = route
                tool_info = self.adapter.introspect_route(path, method, handler, config)
                if not tool_info.hidden:
                    tools.append(
                        MCPTool(
                            name=tool_info.name,
                            description=tool_info.description,
                            inputSchema=tool_info.input_schema,
                        )
                    )
            return tools

        @self._server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
            """Execute a tool by name."""
            # Find the corresponding route
            for route in self.adapter.get_routes():
                path, method, handler, config = route
                tool_info = self.adapter.introspect_route(path, method, handler, config)
                if tool_info.name == name:
                    try:
                        result = self.adapter.execute_tool(handler, arguments)
                        # Return result in MCP format
                        if isinstance(result, (dict, list, str, int, float, bool)):
                            return [json.dumps(result, default=str)]
                        return [str(result)]
                    except Exception as e:
                        return [f"Error: {str(e)}"]
            return [f"Tool not found: {name}"]

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