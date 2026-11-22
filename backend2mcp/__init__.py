"""backend2mcp - Convert Python web backends into MCP servers."""

from backend2mcp.core import BaseAdapter, MCPServer, ToolInfo, mcp_tool

__version__ = "0.2.1"
__author__ = "Satyam Singh"
__license__ = "MIT"

__all__ = [
    "BaseAdapter",
    "ToolInfo",
    "MCPServer",
    "mcp_tool",
    "__version__",
]
