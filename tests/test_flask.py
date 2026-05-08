"""Tests for Flask adapter."""

import pytest
from flask import Flask

from backend2mcp.flask import MCPAdapter
from backend2mcp.flask.adapter import mcp_tool


class TestFlaskBasic:
    """Test basic Flask adapter functionality."""

    @pytest.fixture
    def app(self):
        """Create a simple Flask app for testing."""
        app = Flask(__name__)

        @app.route("/users/<int:id>")
        def get_user(id):
            return {"id": id, "name": "John"}

        @app.route("/users", methods=["POST"])
        def create_user():
            return {"status": "created"}

        @app.route("/search")
        def search():
            return {"results": []}

        return app

    def test_adapter_instantiation(self, app):
        """Test adapter can be created from Flask app."""
        adapter = MCPAdapter(app)
        assert adapter.get_app() is app

    def test_get_routes(self, app):
        """Test getting routes from Flask app."""
        adapter = MCPAdapter(app)
        routes = adapter.get_routes()

        assert len(routes) == 3

        paths = [r[0] for r in routes]
        methods = [r[1] for r in routes]

        assert "/users/<id>" in paths
        assert "/search" in paths
        assert "GET" in methods
        assert "POST" in methods

    def test_build_tool_name(self):
        """Test tool name generation."""
        adapter = MCPAdapter()

        # Simple path
        assert adapter.build_tool_name("GET", "/search") == "get_search"

        # Path with int converter
        assert adapter.build_tool_name("GET", "/users/<int:id>") == "get_by_id"

        # Path with string converter
        assert adapter.build_tool_name("GET", "/items/<string:name>") == "get_by_name"

    def test_introspect_simple_route(self, app):
        """Test introspection of simple route."""
        adapter = MCPAdapter(app)

        for path, method, handler, config in adapter.get_routes():
            if path == "/search" and method == "GET":
                tool_info = adapter.introspect_route(path, method, handler, config)
                assert tool_info.name == "get_search"
                assert tool_info.http_method == "GET"
                assert tool_info.hidden is False
                return

        pytest.fail("Route /search not found")

    def test_introspect_path_param(self, app):
        """Test introspection with path parameters."""
        adapter = MCPAdapter(app)

        for path, method, handler, config in adapter.get_routes():
            if path == "/users/<id>":
                tool_info = adapter.introspect_route(path, method, handler, config)
                props = tool_info.input_schema["properties"]
                assert "id" in props
                assert props["id"]["type"] == "integer"
                return

        pytest.fail("Route /users/<id> not found")


class TestFlaskDecorators:
    """Test @mcp_tool decorator for Flask."""

    @pytest.fixture
    def app_with_decorator(self):
        """Create Flask app with decorated routes."""
        app = Flask(__name__)

        @app.route("/users/<int:id>")
        @mcp_tool(name="get_user_info", description="Get user by ID")
        def get_user(id):
            return {"id": id}

        @app.route("/secret")
        @mcp_tool(hidden=True)
        def secret():
            return {"secret": True}

        return app

    def test_custom_name_via_decorator(self, app_with_decorator):
        """Test custom tool name via decorator."""
        adapter = MCPAdapter(app_with_decorator)

        for path, method, handler, config in adapter.get_routes():
            if path == "/users/<id>":
                tool_info = adapter.introspect_route(path, method, handler, config)
                assert tool_info.name == "get_user_info"
                assert tool_info.description == "Get user by ID"
                return

        pytest.fail("Route not found")

    def test_hidden_via_decorator(self, app_with_decorator):
        """Test hidden flag via decorator."""
        adapter = MCPAdapter(app_with_decorator)

        visible_tools = []
        for path, method, handler, config in adapter.get_routes():
            tool_info = adapter.introspect_route(path, method, handler, config)
            if not tool_info.hidden:
                visible_tools.append(tool_info.name)

        assert "secret" not in visible_tools
        assert "get_user_info" in visible_tools


class TestFlaskExecution:
    """Test tool execution in Flask."""

    @pytest.fixture
    def app_for_execution(self):
        """Create app for execution testing."""
        app = Flask(__name__)

        @app.route("/users/<int:id>")
        def get_user(id):
            return {"id": id, "name": "Test"}

        @app.route("/echo")
        def echo():
            return {"message": "hello"}

        return app

    def test_sync_handler_execution(self, app_for_execution):
        """Test executing sync handler."""
        adapter = MCPAdapter(app_for_execution)

        for path, method, handler, config in adapter.get_routes():
            if path == "/echo":
                result = adapter.execute_tool(handler, {})
                assert result == {"message": "hello"}
                return

        pytest.fail("Route not found")

    def test_path_param_execution(self, app_for_execution):
        """Test executing with path parameters."""
        adapter = MCPAdapter(app_for_execution)

        for path, method, handler, config in adapter.get_routes():
            if path == "/users/<id>":
                result = adapter.execute_tool(handler, {"id": 42})
                assert result["id"] == 42
                return

        pytest.fail("Route not found")


class TestFlaskConverters:
    """Test Flask converter types."""

    @pytest.fixture
    def app_with_converters(self):
        """Create app with various converters."""
        app = Flask(__name__)

        @app.route("/ints/<int:value>")
        def int_route(value):
            return {"value": value}

        @app.route("/floats/<float:value>")
        def float_route(value):
            return {"value": value}

        @app.route("/paths/<path:filepath>")
        def path_route(filepath):
            return {"filepath": filepath}

        @app.route("/uuids/<uuid:id>")
        def uuid_route(id):
            return {"id": str(id)}

        return app

    def test_int_converter_schema(self, app_with_converters):
        """Test integer converter schema."""
        adapter = MCPAdapter(app_with_converters)

        for path, method, handler, config in adapter.get_routes():
            if path == "/ints/<value>":
                tool_info = adapter.introspect_route(path, method, handler, config)
                props = tool_info.input_schema["properties"]
                assert props["value"]["type"] == "integer"
                return

        pytest.fail("Route not found")

    def test_float_converter_schema(self, app_with_converters):
        """Test float converter schema."""
        adapter = MCPAdapter(app_with_converters)

        for path, method, handler, config in adapter.get_routes():
            if path == "/floats/<value>":
                tool_info = adapter.introspect_route(path, method, handler, config)
                props = tool_info.input_schema["properties"]
                assert props["value"]["type"] == "number"
                return

        pytest.fail("Route not found")


class TestFlaskEdgeCases:
    """Test edge cases for Flask adapter."""

    def test_empty_app(self):
        """Test adapter with empty app."""
        app = Flask(__name__)
        adapter = MCPAdapter(app)
        routes = adapter.get_routes()
        assert routes == []

    def test_static_route_excluded(self):
        """Test that static routes are excluded."""
        app = Flask(__name__)
        # Static is added by default in Flask
        assert "static" in [r.endpoint for r in app.url_map.iter_rules()]

        adapter = MCPAdapter(app)
        routes = adapter.get_routes()

        # Static should not be in our routes
        for path, method, handler, config in routes:
            assert path != "/static/<path:filename>"