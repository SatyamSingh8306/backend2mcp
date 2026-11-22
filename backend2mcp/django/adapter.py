"""Django MCP Adapter implementation."""

from __future__ import annotations

import importlib
import inspect
import re
from typing import Any, Callable

from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.auth import AuthContext, AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError, ToolExecutionError
from backend2mcp.core.schema import (
    extract_schema_from_signature,
    route_to_description,
)
from backend2mcp.core.tool import build_tool_name, mcp_tool  # noqa: F401 (re-export)
from backend2mcp.core.utils import normalize_result, prepare_execution_arguments, run_coroutine_sync

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")
_CONVERTER = re.compile(r"<(?:(?P<conv>\w+):)?(?P<name>\w+)>")
_CONVERTER_TYPES = {
    "int": "integer",
    "float": "number",
    "uuid": "string",
    "slug": "string",
    "path": "string",
    "str": "string",
}


def _normalize_django_path(pattern: Any) -> str:
    """Normalise a Django route pattern to ``/users/<id>/`` style."""
    return "/" + _CONVERTER.sub(r"<\g<name>>", str(pattern)).strip("/") + (
        "/" if str(pattern).endswith("/") else ""
    )


class MCPAdapter(BaseAdapter):
    """Expose Django URL patterns as MCP tools."""

    def __init__(
        self,
        urls: list[URLPattern] | None = None,
        app_name: str = "app",
        auth_provider: AuthProvider | None = None,
        server_name: str | None = None,
    ):
        super().__init__(
            auth_provider=auth_provider,
            server_name=server_name or "backend2mcp-django",
        )
        self._urls = urls
        self._app_name = app_name

    def get_app(self) -> Any:
        """Django has no single app object; return the URL resolver."""
        return get_resolver()

    def get_url_patterns(self) -> list[URLPattern]:
        urls = self._urls
        if urls is None:
            try:
                if settings.configured and hasattr(settings, "ROOT_URLCONF"):
                    root_urls = importlib.import_module(settings.ROOT_URLCONF)
                    urls = getattr(root_urls, "urlpatterns", [])
            except Exception:
                urls = []
        if urls is None:
            return []
        return self._flatten_patterns(urls)

    def _flatten_patterns(self, patterns: list[Any]) -> list[URLPattern]:
        result: list[URLPattern] = []
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                result.extend(self._flatten_patterns(pattern.url_patterns))
            elif isinstance(pattern, URLPattern):
                result.append(pattern)
        return result

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        routes: list[tuple[str, str, Callable[..., Any], Any]] = []
        for pattern in self.get_url_patterns():
            try:
                view = pattern.callback
                if view is None:
                    continue
                path = _normalize_django_path(pattern.pattern)

                view_class = getattr(view, "view_class", None)
                if view_class is not None and inspect.isclass(view_class):
                    # Class-based views: one tool per implemented HTTP method.
                    instance = view_class()
                    for method_name in _HTTP_METHODS:
                        method_func = getattr(instance, method_name, None)
                        if callable(method_func):
                            routes.append(
                                (path, method_name.upper(), method_func, pattern)
                            )
                    continue

                if inspect.isclass(view):
                    for method_name in _HTTP_METHODS:
                        method_func = getattr(view, method_name, None)
                        if callable(method_func):
                            routes.append((path, method_name.upper(), method_func, pattern))
                    continue

                method = getattr(pattern, "method", None) or "GET"
                routes.append((path, method.upper(), view, pattern))
            except Exception:
                continue
        return routes

    def introspect_route(
        self, path: str, method: str, handler: Callable[..., Any], config: Any
    ) -> ToolInfo:
        if not isinstance(config, URLPattern):
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
        self, handler: Callable[..., Any], route: URLPattern
    ) -> dict[str, Any]:
        path_params: dict[str, dict[str, Any]] = {}
        converters = getattr(route.pattern, "converters", {}) or {}
        for name, converter in converters.items():
            converter_type = type(converter).__name__.lower()
            json_type = "string"
            for prefix, mapped in _CONVERTER_TYPES.items():
                if prefix in converter_type:
                    json_type = mapped
                    break
            path_params[name] = {"type": json_type}
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
            exec_args = prepare_execution_arguments(handler, arguments, auth_context)
            if inspect.iscoroutinefunction(handler):
                result = run_coroutine_sync(handler(**exec_args))
            else:
                result = handler(**exec_args)
                if inspect.isawaitable(result):
                    result = run_coroutine_sync(result)
            return normalize_result(result)
        except Exception as exc:
            raise ToolExecutionError(f"Failed to execute tool: {exc}") from exc
