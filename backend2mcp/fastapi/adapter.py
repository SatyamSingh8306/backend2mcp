"""FastAPI MCP Adapter implementation."""

import inspect
from enum import Enum
from typing import Any, Callable, get_type_hints

from fastapi import APIRouter, FastAPI
from fastapi.dependencies.utils import get_depends_shallow
from fastapi.routing import APIRoute

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.auth import AuthContext, AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError, SchemaConversionError
from backend2mcp.core.schema import extract_schema_from_signature, route_to_description


class MCPAdapter(BaseAdapter):
    """MCP Adapter for FastAPI applications.

    Example:
        from fastapi import FastAPI
        from backend2mcp.fastapi import MCPAdapter

        app = FastAPI()

        @app.get("/users/{id}")
        async def get_user(id: int):
            return {"id": id, "name": "Satyam"}

        adapter = MCPAdapter(app)
        adapter.run()
    """

    def __init__(
        self,
        app: FastAPI | APIRouter | None = None,
        auth_provider: AuthProvider | None = None,
    ):
        """Initialize the adapter with a FastAPI app and optional auth.

        Args:
            app: FastAPI application or router instance
            auth_provider: Optional auth provider for authentication
        """
        super().__init__(auth_provider=auth_provider)
        self._app = app

    def get_app(self) -> FastAPI | APIRouter:
        """Get the underlying FastAPI app."""
        if self._app is None:
            raise RouteIntrospectionError("No FastAPI app provided")
        return self._app

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        """Get all routes from the FastAPI app."""
        app = self.get_app()
        routes: list[tuple[str, str, Callable[..., Any], Any]] = []

        for route in app.routes:
            if isinstance(route, APIRoute):
                for method in route.methods:
                    if method.lower() in ("get", "post", "put", "patch", "delete", "options"):
                        routes.append(
                            (
                                route.path,
                                method.upper(),
                                route.endpoint,
                                route,
                            )
                        )

        return routes

    def introspect_route(
        self, path: str, method: str, handler: Callable[..., Any], config: Any
    ) -> ToolInfo:
        """Introspect a FastAPI route."""
        if not isinstance(config, APIRoute):
            raise RouteIntrospectionError(f"Invalid route config type: {type(config)}")

        # Check for @mcp_tool decorator
        decorator = getattr(handler, "__mcp_tool__", None)
        if decorator:
            if decorator.get("hidden", False):
                return ToolInfo(
                    name="",
                    description="",
                    route_path=path,
                    http_method=method,
                    handler=handler,
                    input_schema={},
                    hidden=True,
                )

            return ToolInfo(
                name=decorator.get("name", self.build_tool_name(method, path)),
                description=decorator.get(
                    "description", route_to_description(method, path)
                ),
                route_path=path,
                http_method=method,
                handler=handler,
                input_schema=decorator.get(
                    "input_schema", self._extract_input_schema(handler, config)
                ),
                hidden=False,
            )

        # Build tool name and description
        tool_name = self.build_tool_name(method, path)
        description = route_to_description(method, path)
        input_schema = self._extract_input_schema(handler, config)

        return ToolInfo(
            name=tool_name,
            description=description,
            route_path=path,
            http_method=method,
            handler=handler,
            input_schema=input_schema,
            hidden=False,
        )

    def _extract_input_schema(
        self, handler: Callable[..., Any], route: APIRoute
    ) -> dict[str, Any]:
        """Extract MCP input schema from a FastAPI route."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        # Handle path parameters
        for param in route.path_params:
            param_type = route.param_converters[param.name].type_
            from backend2mcp.core.schema import type_to_json_schema

            schema = type_to_json_schema(param_type, param.name)
            properties[param.name] = schema
            required.append(param.name)

        # Handle query parameters
        for param in route.query_params:
            if param in route.dependant.query_params:
                continue  # Already handled through dependencies
            param_info = route.dependant.query_params_dict.get(param)
            if param_info:
                schema = type_to_json_schema(param_info.type_, param)
                if param_info.default is not inspect.Parameter.empty:
                    schema["default"] = param_info.default
                else:
                    required.append(param)
                properties[param] = schema

        # Handle request body
        body_field = route.dependant.body_params
        if body_field:
            body_type = body_field.type_
            from backend2mcp.core.schema import type_to_json_schema

            if hasattr(body_type, "model_fields"):
                # Pydantic model
                for field_name, field_info in body_type.model_fields.items():
                    field_schema = type_to_json_schema(field_info.annotation, field_name)
                    if field_info.is_required():
                        required.append(field_name)
                    properties[field_name] = field_schema
            else:
                # Raw dict/list
                properties["body"] = type_to_json_schema(body_type)

        result: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            result["required"] = required

        return result

    def build_tool_name(self, http_method: str, path: str) -> str:
        """Build a deterministic tool name from method and path."""
        # Convert path to snake_case
        segments = path.strip("/").split("/")
        name_parts = [http_method.lower()]

        for segment in segments:
            if segment.startswith("{") and segment.endswith("}"):
                param_name = segment[1:-1]
                name_parts.append(f"by_{param_name}")
            elif segment:
                name_parts.append(segment.replace("-", "_"))

        # Remove empty parts and join
        name_parts = [p for p in name_parts if p and p != "-"]
        tool_name = "_".join(name_parts)

        # Sanitize: only alphanumeric + underscores
        import re

        tool_name = re.sub(r"[^a-z0-9_]", "", tool_name.lower())

        # Ensure it starts with a letter or underscore
        if tool_name and tool_name[0].isdigit():
            tool_name = f"_{tool_name}"

        return tool_name or "root"

    def execute_tool(
        self,
        handler: Callable[..., Any],
        arguments: dict[str, Any],
        auth_context: AuthContext | None = None,
    ) -> Any:
        """Execute a tool by calling the handler directly.

        Args:
            handler: The route handler function
            arguments: Resolved arguments from MCP request
            auth_context: AuthContext with auth information

        Returns:
            The handler's return value, serialized appropriately
        """
        try:
            # Prepare context-aware arguments
            exec_args = dict(arguments)

            # Inject auth headers if handler expects them
            if auth_context:
                # Add auth context to arguments for handlers that need it
                if "auth_context" in handler.__code__.co_varnames:
                    exec_args["auth_context"] = auth_context

                # Add headers for handlers that expect request-like objects
                if "headers" in handler.__code__.co_varnames:
                    exec_args["headers"] = auth_context.headers

            # Check if handler is async
            if inspect.iscoroutinefunction(handler):
                import asyncio

                result = asyncio.run(handler(**exec_args))
            else:
                result = handler(**exec_args)

            # Handle FastAPI responses
            if hasattr(result, "model_dump"):
                return result.model_dump()
            elif hasattr(result, "json"):
                return result.json()
            elif isinstance(result, dict):
                return result
            else:
                return str(result)

        except Exception as e:
            from backend2mcp.core.exceptions import ToolExecutionError

            raise ToolExecutionError(f"Failed to execute tool: {e}") from e

    def run(self) -> None:
        """Run the MCP server."""
        from backend2mcp.core.server import MCPServer

        server = MCPServer(self, "backend2mcp-fastapi")
        server.run_sync()


def mcp_tool(
    name: str | None = None,
    description: str | None = None,
    input_schema: dict[str, Any] | None = None,
    hidden: bool = False,
) -> Callable:
    """Decorator to customize MCP tool behavior for a route.

    Args:
        name: Custom tool name (defaults to auto-generated)
        description: Custom tool description
        input_schema: Custom input schema
        hidden: Whether to hide this route from MCP

    Returns:
        Decorated function

    Example:
        @app.get("/users/{id}")
        @mcp_tool(name="get_user", description="Get a user by ID")
        async def get_user(id: int):
            return {"id": id, "name": "Satyam"}
    """

    def decorator(func: Callable) -> Callable:
        func.__mcp_tool__ = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "hidden": hidden,
        }
        return func

    return decorator