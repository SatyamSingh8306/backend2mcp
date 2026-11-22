"""Sanic MCP Adapter implementation."""

from __future__ import annotations

from typing import Any, Callable

from sanic import Sanic

from backend2mcp.core.auth import AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError
from backend2mcp.core.simple import SimpleAdapter
from backend2mcp.core.tool import mcp_tool  # noqa: F401 (re-export)
from backend2mcp.core.tool import normalize_route_path

__all__ = ["MCPAdapter", "mcp_tool"]


class MCPAdapter(SimpleAdapter):
    """Expose a Sanic application as MCP tools."""

    framework_name = "sanic"

    def __init__(
        self,
        app: Sanic | None = None,
        auth_provider: AuthProvider | None = None,
        server_name: str | None = None,
    ):
        super().__init__(
            app=app,
            auth_provider=auth_provider,
            server_name=server_name or "backend2mcp-sanic",
        )

    def get_app(self) -> Sanic:
        app = super().get_app()
        if not isinstance(app, Sanic):
            raise RouteIntrospectionError(f"Expected a Sanic app, got {type(app)}")
        return app

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        routes: list[tuple[str, str, Callable[..., Any], Any]] = []
        for route in self.get_app().router.routes:
            handler = getattr(route, "handler", None)
            if handler is None:
                continue
            path = normalize_route_path(getattr(route, "uri", "/") or "/")
            methods = getattr(route, "methods", ()) or ()
            for method in sorted(methods):
                if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                    routes.append((path, method.upper(), handler, route))
        return routes
