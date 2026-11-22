"""Bottle MCP Adapter implementation."""

from __future__ import annotations

import re
from typing import Any, Callable

from bottle import Bottle

from backend2mcp.core.auth import AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError
from backend2mcp.core.simple import SimpleAdapter
from backend2mcp.core.tool import mcp_tool  # noqa: F401 (re-export)
from backend2mcp.core.tool import normalize_route_path

_COLON_PARAM = re.compile(r":(\w+)")


class MCPAdapter(SimpleAdapter):
    """Expose a Bottle application as MCP tools."""

    framework_name = "bottle"

    def __init__(
        self,
        app: Bottle | None = None,
        auth_provider: AuthProvider | None = None,
        server_name: str | None = None,
    ):
        super().__init__(
            app=app,
            auth_provider=auth_provider,
            server_name=server_name or "backend2mcp-bottle",
        )

    def get_app(self) -> Bottle:
        app = super().get_app()
        if not isinstance(app, Bottle):
            raise RouteIntrospectionError(f"Expected a Bottle app, got {type(app)}")
        return app

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        routes: list[tuple[str, str, Callable[..., Any], Any]] = []
        for route in self.get_app().routes:
            callback = getattr(route, "callback", None)
            if callback is None:
                continue
            # Bottle supports both ``/:id`` and ``/<id>`` path syntaxes.
            path = normalize_route_path(_COLON_PARAM.sub(r"<\1>", route.rule))
            methods = route.method
            if isinstance(methods, str):
                methods = [methods]
            for method in methods or ():
                if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                    routes.append((path, method.upper(), callback, route))
        return routes
