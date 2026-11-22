"""FastAPI MCP Adapter implementation."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.auth import AuthContext, AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError, ToolExecutionError
from backend2mcp.core.schema import (
    _json_safe,
    extract_schema_from_signature,
    route_to_description,
    schema_from_path,
    type_to_json_schema,
)
from backend2mcp.core.tool import build_tool_name, mcp_tool  # noqa: F401 (re-export)

__all__ = ["MCPAdapter", "mcp_tool"]
from backend2mcp.core.utils import (
    normalize_result,
    prepare_execution_arguments,
    run_coroutine_sync,
)

_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


def _field_annotation(field: Any) -> Any:
    """Get the annotation of a FastAPI dependant field across versions."""
    field_info = getattr(field, "field_info", None)
    annotation = getattr(field_info, "annotation", None)
    if annotation is None or annotation is inspect.Parameter.empty:
        annotation = getattr(field, "type_", None)
    if annotation is None or annotation is inspect.Parameter.empty:
        annotation = str
    return annotation


def _field_default(field: Any) -> tuple[bool, Any]:
    """Return ``(has_default, value)`` for a FastAPI dependant field."""
    field_info = getattr(field, "field_info", None)
    if field_info is None:
        return False, None
    try:
        if field_info.is_required():
            return False, None
    except AttributeError:
        pass
    default = getattr(field_info, "default", PydanticUndefined)
    if default is PydanticUndefined:
        return False, None
    return True, default


class MCPAdapter(BaseAdapter):
    """Expose a FastAPI app (or router) as MCP tools.

    Example:
        from fastapi import FastAPI
        from backend2mcp.fastapi import MCPAdapter

        app = FastAPI()

        @app.get("/users/{id}")
        async def get_user(id: int):
            return {"id": id, "name": "Satyam"}

        MCPAdapter(app).run()
    """

    def __init__(
        self,
        app: FastAPI | APIRouter | None = None,
        auth_provider: AuthProvider | None = None,
        server_name: str | None = None,
    ):
        super().__init__(
            auth_provider=auth_provider,
            server_name=server_name or "backend2mcp-fastapi",
        )
        self._app = app

    def get_app(self) -> FastAPI | APIRouter:
        if self._app is None:
            raise RouteIntrospectionError("No FastAPI app provided")
        return self._app

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        app = self.get_app()
        routes: list[tuple[str, str, Callable[..., Any], Any]] = []
        for route in getattr(app, "routes", []):
            if not isinstance(route, APIRoute):
                continue
            endpoint = getattr(route, "endpoint", None)
            if endpoint is None:
                continue
            for method in sorted(getattr(route, "methods", ()) or ()):
                if method.upper() in _HTTP_METHODS:
                    routes.append((route.path, method.upper(), endpoint, route))
        return routes

    def introspect_route(
        self, path: str, method: str, handler: Callable[..., Any], config: Any
    ) -> ToolInfo:
        if not isinstance(config, APIRoute):
            raise RouteIntrospectionError(f"Invalid route config type: {type(config)}")

        decorator = getattr(handler, "__mcp_tool__", None) or {}
        schema = decorator.get("input_schema")
        if not schema:
            schema = self._extract_input_schema(path, handler, config)

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
        self, path: str, handler: Callable[..., Any], route: APIRoute
    ) -> dict[str, Any]:
        """Extract an MCP input schema from a FastAPI route."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        dependant = getattr(route, "dependant", None)

        if dependant is not None:
            # Path parameters.
            for field in getattr(dependant, "path_params", ()):
                name = getattr(field, "name", None)
                if not name:
                    continue
                properties[name] = type_to_json_schema(_field_annotation(field), name)
                required.append(name)

            # Query parameters.
            for field in getattr(dependant, "query_params", ()):
                name = getattr(field, "name", None)
                if not name or name in properties:
                    continue
                if name in ("request", "self", "headers", "auth_context"):
                    continue
                field_schema = type_to_json_schema(_field_annotation(field), name)
                has_default, default = _field_default(field)
                if has_default:
                    field_schema["default"] = _json_safe(default)
                else:
                    required.append(name)
                properties[name] = field_schema

            # Request bodies (Pydantic models are flattened).
            for field in getattr(dependant, "body_params", ()):
                body_type = _field_annotation(field)
                name = getattr(field, "name", None) or "body"
                if inspect.isclass(body_type) and issubclass(body_type, BaseModel):
                    model_schema = type_to_json_schema(body_type)
                    for field_name, field_schema in model_schema.get("properties", {}).items():
                        properties[field_name] = field_schema
                    required.extend(model_schema.get("required", []))
                else:
                    properties[name] = type_to_json_schema(body_type, name)
                    has_default, default = _field_default(field)
                    if has_default:
                        properties[name]["default"] = _json_safe(default)
                    elif body_type is not type(None):
                        required.append(name)
        else:
            # Very old FastAPI versions / APIRouter fallback.
            properties = extract_schema_from_signature(
                handler, path_params=schema_from_path(path)
            )["properties"]
            required = extract_schema_from_signature(
                handler, path_params=schema_from_path(path)
            ).get("required", [])

        # De-duplicate the required list while preserving order.
        required = list(dict.fromkeys(required))
        result: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            result["required"] = required
        return result

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
