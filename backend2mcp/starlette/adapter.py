"""Starlette MCP Adapter implementation."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from starlette.applications import Starlette
from starlette.routing import Route

from backend2mcp.core.auth import AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError
from backend2mcp.core.simple import SimpleAdapter
from backend2mcp.core.tool import mcp_tool  # noqa: F401 (re-export)
from backend2mcp.core.tool import normalize_route_path

__all__ = ["MCPAdapter", "mcp_tool"]

_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


class MCPAdapter(SimpleAdapter):
    """Expose a Starlette application as MCP tools."""

    framework_name = "starlette"

    def __init__(
        self,
        app: Starlette | None = None,
        auth_provider: AuthProvider | None = None,
        server_name: str | None = None,
    ):
        super().__init__(
            app=app,
            auth_provider=auth_provider,
            server_name=server_name or "backend2mcp-starlette",
        )

    def get_app(self) -> Starlette:
        app = super().get_app()
        if not isinstance(app, Starlette):
            raise RouteIntrospectionError(f"Expected a Starlette app, got {type(app)}")
        return app

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        routes: list[tuple[str, str, Callable[..., Any], Any]] = []
        for route in getattr(self.get_app(), "routes", []):
            if not isinstance(route, Route):
                continue  # Mounts, WebSocketRoute, etc. are not MCP tools.
            endpoint = route.endpoint
            if endpoint is None:
                continue
            path = normalize_route_path(route.path)
            for method in sorted(getattr(route, "methods", ()) or ()):
                if method.upper() in _HTTP_METHODS:
                    routes.append((path, method.upper(), endpoint, route))
        return routes
