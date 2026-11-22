"""aiohttp MCP Adapter implementation."""

from __future__ import annotations

from typing import Any, Callable

from aiohttp import web

from backend2mcp.core.auth import AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError
from backend2mcp.core.simple import SimpleAdapter
from backend2mcp.core.tool import mcp_tool  # noqa: F401 (re-export)
from backend2mcp.core.tool import normalize_route_path

_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


class MCPAdapter(SimpleAdapter):
    """Expose an aiohttp application as MCP tools."""

    framework_name = "aiohttp"

    def __init__(
        self,
        app: web.Application | None = None,
        auth_provider: AuthProvider | None = None,
        server_name: str | None = None,
    ):
        super().__init__(
            app=app,
            auth_provider=auth_provider,
            server_name=server_name or "backend2mcp-aiohttp",
        )

    def get_app(self) -> web.Application:
        app = super().get_app()
        if not isinstance(app, web.Application):
            raise RouteIntrospectionError(f"Expected an aiohttp Application, got {type(app)}")
        return app

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        routes: list[tuple[str, str, Callable[..., Any], Any]] = []
        for route in self.get_app().router.routes():
            method = getattr(route, "method", None)
            if not method or method.upper() not in _HTTP_METHODS:
                continue
            handler = getattr(route, "handler", None)
            if handler is None:
                continue
            resource = getattr(route, "resource", None)
            path = normalize_route_path(getattr(resource, "canonical", "/"))
            routes.append((path, method.upper(), handler, route))
        return routes
