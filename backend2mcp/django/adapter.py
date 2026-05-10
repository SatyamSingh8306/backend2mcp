"""Django MCP Adapter implementation."""

import inspect
from typing import Any, Callable

from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.auth import AuthContext, AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError
from backend2mcp.core.schema import route_to_description


class MCPAdapter(BaseAdapter):
    """MCP Adapter for Django applications.

    Example:
        from django.urls import path
        from backend2mcp.django import MCPAdapter

        urlpatterns = [
            path("users/<int:id>/", views.get_user),
        ]

        adapter = MCPAdapter()
        adapter.run()
    """

    def __init__(
        self,
        urls: list[URLPattern] | None = None,
        app_name: str = "app",
        auth_provider: AuthProvider | None = None,
    ):
        """Initialize the adapter with Django URL patterns and optional auth.

        Args:
            urls: List of URL patterns (defaults to project's ROOT_URLCONF)
            app_name: App name for namespace
            auth_provider: Optional auth provider for authentication
        """
        super().__init__(auth_provider=auth_provider)
        self._urls = urls
        self._app_name = app_name

    def get_app(self) -> Any:
        """Django doesn't have a single app object - return the resolver."""
        return get_resolver()

    def get_url_patterns(self) -> list[URLPattern]:
        """Get all URL patterns from Django."""
        urls = self._urls

        if urls is None:
            # Try to get from ROOT_URLCONF setting
            try:
                from django.conf import settings

                if hasattr(settings, "ROOT_URLCONF"):
                    import importlib

                    root_urls = importlib.import_module(settings.ROOT_URLCONF)
                    urls = getattr(root_urls, "urlpatterns", [])
            except Exception:
                pass

        if urls is None:
            return []

        return self._flatten_patterns(urls)

    def _flatten_patterns(
        self, patterns: list[URLPattern | URLResolver]
    ) -> list[URLPattern]:
        """Flatten nested URL patterns into a list."""
        result: list[URLPattern] = []

        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                # Include nested patterns
                result.extend(self._flatten_patterns(pattern.url_patterns))
            elif isinstance(pattern, URLPattern):
                result.append(pattern)

        return result

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        """Get all routes from Django URL patterns."""
        routes: list[tuple[str, str, Callable[..., Any], Any]] = []

        for pattern in self.get_url_patterns():
            try:
                method = getattr(pattern, "method", None) or "GET"
                view = pattern.callback
                name = getattr(pattern, "name", None)

                # Skip unnamed patterns with no view
                if view is None:
                    continue

                # Handle class-based views
                if inspect.isclass(view):
                    # CBV: inspect its methods
                    for http_method in ["get", "post", "put", "patch", "delete"]:
                        method_func = getattr(view, http_method, None)
                        if method_func and callable(method_func):
                            http_verb = http_method.upper()
                            # Build pattern with _method suffix
                            pattern_key = f"{pattern.pattern}::{http_method}"
                            routes.append(
                                (
                                    f"/{pattern.pattern}",
                                    http_verb,
                                    method_func,
                                    pattern,
                                )
                            )
                else:
                    routes.append(
                        (
                            f"/{pattern.pattern}",
                            method.upper() if method else "GET",
                            view,
                            pattern,
                        )
                    )
            except Exception:
                continue

        return routes

    def introspect_route(
        self, path: str, method: str, handler: Callable[..., Any], config: Any
    ) -> ToolInfo:
        """Introspect a Django route."""
        if not isinstance(config, URLPattern):
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
        self, handler: Callable[..., Any], route: URLPattern
    ) -> dict[str, Any]:
        """Extract MCP input schema from a Django route."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        # Extract path converters
        pattern = route.pattern
        if hasattr(pattern, "converters"):
            for param_name, converter in pattern.converters.items():
                converter_type = type(converter).__name__.lower()
                type_map = {
                    "intconverter": ("integer", 0),
                    "floatconverter": ("number", 0.0),
                    "strconverter": ("string", ""),
                    "uuidconverter": ("string", ""),
                    "slugconverter": ("string", ""),
                    "pathconverter": ("string", ""),
                }
                json_type, default = type_map.get(
                    converter_type, ("string", "")
                )
                properties[param_name] = {"type": json_type}
                required.append(param_name)

        # Extract from handler signature
        try:
            sig = inspect.signature(handler)
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "request", "args", "kwargs"):
                    continue
                if param_name in properties:
                    continue
                if param.default is not inspect.Parameter.empty:
                    properties[param_name] = {
                        "type": "string",
                        "default": param.default,
                    }
                else:
                    properties[param_name] = {"type": "string"}
                    required.append(param_name)
        except Exception:
            pass

        result: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            result["required"] = required

        return result

    def build_tool_name(self, http_method: str, path: str) -> str:
        """Build a deterministic tool name from method and path."""
        # Clean the path - Django paths may have converters like <int:id>
        import re

        # Remove path converters: <int:id> -> id
        path_cleaned = re.sub(r"<\w+:(\w+)>", r"by_\1", path)
        segments = path_cleaned.strip("/").split("/")
        name_parts = [http_method.lower()]

        for segment in segments:
            if segment and segment != "":
                clean_seg = segment.replace("-", "_")
                name_parts.append(clean_seg)

        # Remove empty parts
        name_parts = [p for p in name_parts if p and p != "-"]
        tool_name = "_".join(name_parts)

        # Sanitize
        tool_name = re.sub(r"[^a-z0-9_]", "", tool_name.lower())

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

        Note: Django handlers can be sync or async.

        Args:
            handler: The route handler function
            arguments: Resolved arguments from MCP request
            auth_context: AuthContext with auth information
        """
        try:
            # Prepare execution arguments
            exec_args = dict(arguments)

            # Inject auth context if handler expects it
            if auth_context:
                if "auth_context" in handler.__code__.co_varnames:
                    exec_args["auth_context"] = auth_context

                # Add headers for handlers that expect request with headers
                if "headers" in handler.__code__.co_varnames:
                    exec_args["headers"] = auth_context.headers

            # Check if handler is async (Django 3.1+)
            if inspect.iscoroutinefunction(handler):
                import asyncio

                result = asyncio.run(handler(**exec_args))
            else:
                result = handler(**exec_args)

            # Handle Django REST Framework responses
            if hasattr(result, "data"):
                return result.data
            elif hasattr(result, "content"):
                return result.content.decode()
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

        server = MCPServer(self, "backend2mcp-django")
        server.run_sync()


def mcp_tool(
    name: str | None = None,
    description: str | None = None,
    input_schema: dict[str, Any] | None = None,
    hidden: bool = False,
) -> Callable:
    """Decorator to customize MCP tool behavior for a Django view.

    Args:
        name: Custom tool name (defaults to auto-generated)
        description: Custom tool description
        input_schema: Custom input schema
        hidden: Whether to hide this route from MCP

    Returns:
        Decorated function

    Example:
        from django.views import View
        from backend2mcp.django import mcp_tool

        class UserView(View):
            @mcp_tool(name="get_user", description="Get a user by ID")
            def get(self, request, id: int):
                return JsonResponse({"id": id, "name": "Satyam"})
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