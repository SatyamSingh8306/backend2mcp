"""Flask MCP Adapter implementation."""

from __future__ import annotations

import inspect
import re
from typing import Any, Callable

from flask import Flask
from werkzeug.routing import Rule

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.auth import AuthContext, AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError, ToolExecutionError
from backend2mcp.core.schema import (
    extract_schema_from_signature,
    route_to_description,
    type_to_json_schema,
)
from backend2mcp.core.tool import build_tool_name, mcp_tool  # noqa: F401 (re-export)

__all__ = ["MCPAdapter", "mcp_tool"]
from backend2mcp.core.utils import normalize_result, prepare_execution_arguments, run_coroutine_sync

_CONVERTER_ARG = re.compile(r"<(?:(?P<conv>[\w.]+(?:\([^>]*\))?):)?(?P<name>\w+)>")


def _normalize_flask_path(rule: str) -> str:
    """Strip Werkzeug converter names: ``/users/<int:id>`` -> ``/users/<id>``."""
    return _CONVERTER_ARG.sub(r"<\g<name>>", rule)


def _converter_json_type(converter: Any) -> str:
    name = type(converter).__name__.lower()
    if "integer" in name or name.startswith("int"):
        return "integer"
    if "float" in name or "decimal" in name:
        return "number"
    if "uuid" in name:
        return "string"
    return "string"


class MCPAdapter(BaseAdapter):
    """Expose a Flask application as MCP tools."""

    def __init__(
        self,
        app: Flask | None = None,
        auth_provider: AuthProvider | None = None,
        server_name: str | None = None,
    ):
        super().__init__(
            auth_provider=auth_provider,
            server_name=server_name or "backend2mcp-flask",
        )
        self._app = app

    def get_app(self) -> Flask:
        if self._app is None:
            raise RouteIntrospectionError("No Flask app provided")
        return self._app

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
                    (_normalize_flask_path(rule.rule), method.upper(), view_func, rule)
                )
        return routes

    def introspect_route(
        self, path: str, method: str, handler: Callable[..., Any], config: Any
    ) -> ToolInfo:
        if not isinstance(config, Rule):
            raise RouteIntrospectionError(f"Invalid route config type: {type(config)}")

        decorator = getattr(handler, "__mcp_tool__", None) or {}
        schema = decorator.get("input_schema")
        if not schema:
            schema = self._extract_input_schema(handler, config)

        return ToolInfo(
            name=decorator.get("name") or self.build_tool_name(method, path),
            description=decorator.get("description") or route_to_description(method, path),
            route_path=path,
            http_method=method,
            handler=handler,
            input_schema=schema,
            hidden=bool(decorator.get("hidden", False)),
            required_permissions=list(decorator.get("required_permissions") or []),
            tags=list(decorator.get("tags") or []),
        )

    def _extract_input_schema(
        self, handler: Callable[..., Any], route: Rule
    ) -> dict[str, Any]:
        path_params: dict[str, dict[str, Any]] = {}
        converters = getattr(route, "_converters", {}) or {}
        for name in getattr(route, "arguments", ()) or converters.keys():
            converter = converters.get(name)
            path_params[name] = {
                "type": _converter_json_type(converter) if converter is not None else "string"
            }
        return extract_schema_from_signature(handler, path_params=path_params)

    def build_tool_name(self, http_method: str, path: str) -> str:
        return build_tool_name(http_method, path)

    def execute_tool(
        self,
        handler: Callable[..., Any],
        arguments: dict[str, Any],
        auth_context: AuthContext | None = None,
    ) -> Any:
        try:
            app = self.get_app()
            exec_args = prepare_execution_arguments(handler, arguments, auth_context)
            headers = {
                str(key): str(value)
                for key, value in (auth_context.headers if auth_context else {}).items()
            }
            with app.app_context():
                with app.test_request_context(
                    "/", json=dict(arguments), query_string=dict(arguments), headers=headers
                ):
                    if inspect.iscoroutinefunction(handler):
                        result = run_coroutine_sync(handler(**exec_args))
                    else:
                        result = handler(**exec_args)
                        if inspect.isawaitable(result):
                            result = run_coroutine_sync(result)
            return normalize_result(result)
        except Exception as exc:
            raise ToolExecutionError(f"Failed to execute tool: {exc}") from exc
