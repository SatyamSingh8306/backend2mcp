"""Quart MCP Adapter implementation."""

from __future__ import annotations

import re
from typing import Any, Callable

from quart import Quart

from backend2mcp.core.auth import AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError
from backend2mcp.core.schema import extract_schema_from_signature
from backend2mcp.core.simple import SimpleAdapter
from backend2mcp.core.tool import mcp_tool  # noqa: F401 (re-export)
from backend2mcp.core.tool import normalize_route_path

_CONVERTER_ARG = re.compile(r"<(?:(?P<conv>[\w.]+(?:\([^>]*\))?):)?(?P<name>\w+)>")

_CONVERTER_TYPES = {
    "int": "integer",
    "float": "number",
    "uuid": "string",
    "path": "string",
}


class MCPAdapter(SimpleAdapter):
    """Expose a Quart application as MCP tools."""

    framework_name = "quart"

    def __init__(
        self,
        app: Quart | None = None,
        auth_provider: AuthProvider | None = None,
        server_name: str | None = None,
    ):
        super().__init__(
            app=app,
            auth_provider=auth_provider,
            server_name=server_name or "backend2mcp-quart",
        )

    def get_app(self) -> Quart:
        app = super().get_app()
        if not isinstance(app, Quart):
            raise RouteIntrospectionError(f"Expected a Quart app, got {type(app)}")
        return app

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        app = self.get_app()
        routes: list[tuple[str, str, Callable[..., Any], Any]] = []
        for rule in app.url_map.iter_rules():
            endpoint = getattr(rule, "endpoint", None)
            if endpoint in (None, "static"):
                continue
            view_func = app.view_functions.get(endpoint)
            if view_func is None:
                continue
            methods = set(rule.methods or ())
            methods.difference_update(("HEAD", "OPTIONS"))
            for method in sorted(methods):
                routes.append(
                    (normalize_route_path(_CONVERTER_ARG.sub(r"<\g<name>>", rule.rule)),
                     method.upper(), view_func, rule)
                )
        return routes

    def _extract_input_schema(
        self, handler: Callable[..., Any], path: str = ""
    ) -> dict[str, Any]:
        path_params: dict[str, dict[str, Any]] = {}
        for name in re.findall(r"<(?P<name>\w+)>", path):
            path_params[name] = {"type": "string"}
        return extract_schema_from_signature(handler, path_params=path_params or None)
