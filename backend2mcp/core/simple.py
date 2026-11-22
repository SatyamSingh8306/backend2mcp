"""A reusable adapter base for small/simple web frameworks.

Framework packages only need to implement :meth:`get_routes` and set
``framework_name``; route introspection, naming, auth injection and execution
are provided here.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.auth import AuthContext, AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError, ToolExecutionError
from backend2mcp.core.schema import (
    extract_schema_from_signature,
    route_to_description,
    schema_from_path,
)
from backend2mcp.core.tool import build_tool_name, mcp_tool  # noqa: F401 (re-export)
from backend2mcp.core.utils import (
    normalize_result,
    prepare_execution_arguments,
    run_coroutine_sync,
)


class SimpleAdapter(BaseAdapter):
    """Route-agnostic adapter built on signature introspection."""

    framework_name = "generic"

    def __init__(
        self,
        app: Any = None,
        auth_provider: AuthProvider | None = None,
        server_name: str | None = None,
    ):
        super().__init__(auth_provider=auth_provider, server_name=server_name)
        self._app = app

    def get_app(self) -> Any:
        if self._app is None:
            raise RouteIntrospectionError(f"No application provided to {type(self).__name__}")
        return self._app

    def build_tool_name(self, http_method: str, path: str) -> str:
        return build_tool_name(http_method, path)

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        raise NotImplementedError("Subclasses must implement get_routes()")

    def introspect_route(
        self, path: str, method: str, handler: Callable[..., Any], config: Any
    ) -> ToolInfo:
        decorator = getattr(handler, "__mcp_tool__", None) or {}
        hidden = bool(decorator.get("hidden", False))
        return ToolInfo(
            name=decorator.get("name") or self.build_tool_name(method, path),
            description=decorator.get("description") or route_to_description(method, path),
            route_path=path,
            http_method=method,
            handler=handler,
            input_schema=decorator.get("input_schema") or self._extract_input_schema(handler, path),
            hidden=hidden,
            required_permissions=list(decorator.get("required_permissions") or []),
            tags=list(decorator.get("tags") or []),
        )

    def _extract_input_schema(
        self, handler: Callable[..., Any], path: str = ""
    ) -> dict[str, Any]:
        path_params = schema_from_path(path) if path else None
        return extract_schema_from_signature(handler, path_params=path_params)

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
