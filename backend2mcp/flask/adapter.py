"""Flask MCP Adapter implementation."""

import inspect
from typing import Any, Callable

from flask import Flask, Request, request
from werkzeug.routing import Map, Rule

from backend2mcp.core.adapter import BaseAdapter, ToolInfo
from backend2mcp.core.auth import AuthContext, AuthProvider
from backend2mcp.core.exceptions import RouteIntrospectionError, SchemaConversionError
from backend2mcp.core.schema import extract_schema_from_signature, route_to_description


class MCPAdapter(BaseAdapter):
    """MCP Adapter for Flask applications.

    Example:
        from flask import Flask
        from backend2mcp.flask import MCPAdapter

        app = Flask(__name__)

        @app.route("/users/<int:id>")
        def get_user(id):
            return {"id": id, "name": "Satyam"}

        adapter = MCPAdapter(app)
        adapter.run()
    """

    def __init__(
        self,
        app: Flask | None = None,
        auth_provider: AuthProvider | None = None,
    ):
        """Initialize the adapter with a Flask app and optional auth.

        Args:
            app: Flask application instance
            auth_provider: Optional auth provider for authentication
        """
        super().__init__(auth_provider=auth_provider)
        self._app = app

    def get_app(self) -> Flask:
        """Get the underlying Flask app."""
        if self._app is None:
            raise RouteIntrospectionError("No Flask app provided")
        return self._app

    def get_routes(self) -> list[tuple[str, str, Callable[..., Any], Any]]:
        """Get all routes from the Flask app."""
        app = self.get_app()
        routes: list[tuple[str, str, Callable[..., Any], Any]] = []

        for rule in app.url_map.iter_rules():
            # Skip built-in endpoints
            if rule.endpoint in ("static",):
                continue

            # Get the view function
            view_func = app.view_functions.get(rule.endpoint)
            if view_func is None:
                continue

            # Get methods (Flask uses upper case)
            methods = set(rule.methods or [])
            methods.difference_update(("HEAD", "OPTIONS"))

            for method in methods:
                routes.append(
                    (
                        rule.rule,
                        method.upper(),
                        view_func,
                        rule,
                    )
                )

        return routes

    def introspect_route(
        self, path: str, method: str, handler: Callable[..., Any], config: Any
    ) -> ToolInfo:
        """Introspect a Flask route."""
        if not isinstance(config, Rule):
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
        self, handler: Callable[..., Any], route: Rule
    ) -> dict[str, Any]:
        """Extract MCP input schema from a Flask route."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        # Handle path parameters
        for param in route._converters.values():
            param_name = param.key
            converter_map = {
                "int": ("integer", 0),
                "float": ("number", 0.0),
                "string": ("string", ""),
                "path": ("string", ""),
                "uuid": ("string", ""),
            }
            converter_type = type(param).__name__.replace("Converter", "").lower()
            if converter_type in converter_map:
                json_type, default = converter_map[converter_type]
                properties[param_name] = {"type": json_type}
                required.append(param_name)
            else:
                properties[param_name] = {"type": "string"}
                required.append(param_name)

        # Handle query parameters - check handler signature
        sig = inspect.signature(handler)
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "request"):
                continue
            # Query params typically have Request or specific types
            if param_name not in properties:
                if param.default is not inspect.Parameter.empty:
                    properties[param_name] = {
                        "type": "string",
                        "default": param.default,
                    }
                else:
                    properties[param_name] = {"type": "string"}
                    required.append(param_name)

        result: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            result["required"] = required

        return result

    def build_tool_name(self, http_method: str, path: str) -> str:
        """Build a deterministic tool name from method and path."""
        segments = path.strip("/").split("/")
        name_parts = [http_method.lower()]

        for segment in segments:
            if segment.startswith("<") and segment.endswith(">"):
                # Handle Flask converters: <int:name> or <name>
                if ":" in segment:
                    _, param_name = segment[1:-1].split(":", 1)
                else:
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

        Note: Flask handlers are always synchronous.

        Args:
            handler: The route handler function
            arguments: Resolved arguments from MCP request
            auth_context: AuthContext with auth information
        """
        try:
            from flask import Flask

            app = self.get_app()
            with app.app_context():
                # Import werkzeug's Local proxy
                from werkzeug.local import LocalProxy

                # Prepare execution arguments
                exec_args = dict(arguments)

                # Inject auth context if handler expects it
                if auth_context:
                    if "auth_context" in handler.__code__.co_varnames:
                        exec_args["auth_context"] = auth_context

                    # Add headers for handlers that expect them
                    if "headers" in handler.__code__.co_varnames:
                        exec_args["headers"] = auth_context.headers

                    # Create mock request with auth headers
                    if "request" in handler.__code__.co_varnames:
                        from typing import Optional
                        from werkzeug.datastructures import MultiDict

                        class MockRequest:
                            def __init__(self, args, headers):
                                self.args = MultiDict(args)
                                self.headers = type("Headers", (), headers)()

                        exec_args["request"] = MockRequest(exec_args, auth_context.headers)

                result = handler(**exec_args)

                # Flask can return dicts (JSON) or responses
                if hasattr(result, "get_json"):
                    return result.get_json()
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

        server = MCPServer(self, "backend2mcp-flask")
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
        @app.route("/users/<int:id>")
        @mcp_tool(name="get_user", description="Get a user by ID")
        def get_user(id):
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