"""Tests for FastAPI adapter."""

import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from backend2mcp.fastapi import MCPAdapter
from backend2mcp.fastapi.adapter import mcp_tool


class TestFastAPIBasic:
    """Test basic FastAPI adapter functionality."""

    @pytest.fixture
    def app(self):
        """Create a simple FastAPI app for testing."""
        app = FastAPI()

        @app.get("/users/{id}")
        async def get_user(id: int):
            return {"id": id, "name": "John"}

        @app.post("/users")
        async def create_user(name: str, age: int = 18):
            return {"name": name, "age": age}

        @app.get("/search")
        async def search(query: str, limit: int = 10):
            return {"query": query, "limit": limit}

        return app

    def test_adapter_instantiation(self, app):
        """Test adapter can be created from FastAPI app."""
        adapter = MCPAdapter(app)
        assert adapter.get_app() is app

    def test_get_routes(self, app):
        """Test getting routes from FastAPI app."""
        adapter = MCPAdapter(app)
        routes = adapter.get_routes()

        assert len(routes) == 3

        paths = [r[0] for r in routes]
        methods = [r[1] for r in routes]

        assert "/users/{id}" in paths
        assert "/users" in paths
        assert "/search" in paths

        assert "GET" in methods
        assert "POST" in methods

    def test_build_tool_name(self):
        """Test tool name generation."""
        adapter = MCPAdapter()

        # Simple path
        assert adapter.build_tool_name("GET", "/search") == "get_search"

        # Path with param
        assert adapter.build_tool_name("GET", "/users/{id}") == "get_by_id"

        # POST with param
        assert adapter.build_tool_name("POST", "/users/{id}") == "post_by_id"

        # DELETE
        assert adapter.build_tool_name("DELETE", "/users/{id}") == "delete_by_id"

    def test_introspect_simple_route(self, app):
        """Test introspection of simple route."""
        adapter = MCPAdapter(app)

        # Find the search route
        for path, method, handler, config in adapter.get_routes():
            if path == "/search" and method == "GET":
                tool_info = adapter.introspect_route(path, method, handler, config)
                assert tool_info.name == "get_search"
                assert tool_info.http_method == "GET"
                assert tool_info.route_path == "/search"
                assert tool_info.hidden is False
                assert "inputSchema" in tool_info.input_schema
                assert "properties" in tool_info.input_schema
                return

        pytest.fail("Route /search not found")

    def test_introspect_path_param(self, app):
        """Test introspection with path parameters."""
        adapter = MCPAdapter(app)

        for path, method, handler, config in adapter.get_routes():
            if path == "/users/{id}" and method == "GET":
                tool_info = adapter.introspect_route(path, method, handler, config)
                assert "id" in tool_info.input_schema["properties"]
                assert tool_info.input_schema["properties"]["id"]["type"] == "integer"
                return

        pytest.fail("Route /users/{id} not found")

    def test_introspect_with_defaults(self, app):
        """Test introspection with default values."""
        adapter = MCPAdapter(app)

        for path, method, handler, config in adapter.get_routes():
            if path == "/users" and method == "POST":
                tool_info = adapter.introspect_route(path, method, handler, config)
                assert "name" in tool_info.input_schema["properties"]
                assert "age" in tool_info.input_schema["properties"]
                assert "default" in tool_info.input_schema["properties"]["age"]
                return

        pytest.fail("Route /users not found")


class TestFastAPIPydantic:
    """Test Pydantic model support."""

    @pytest.fixture
    def app_with_models(self):
        """Create FastAPI app with Pydantic models."""

        class UserCreate(BaseModel):
            name: str
            email: str

        class UserResponse(BaseModel):
            id: int
            name: str
            email: str

        app = FastAPI()

        @app.post("/users", response_model=UserResponse)
        async def create_user(user: UserCreate) -> UserResponse:
            return UserResponse(id=1, **user.model_dump())

        return app

    def test_pydantic_body_schema(self, app_with_models):
        """Test schema extraction from Pydantic models."""
        adapter = MCPAdapter(app_with_models)

        for path, method, handler, config in adapter.get_routes():
            if path == "/users" and method == "POST":
                tool_info = adapter.introspect_route(path, method, handler, config)
                props = tool_info.input_schema["properties"]
                assert "name" in props
                assert "email" in props
                return

        pytest.fail("Route /users not found")


class TestFastAPIDecorator:
    """Test @mcp_tool decorator."""

    @pytest.fixture
    def app_with_decorator(self):
        """Create FastAPI app with decorated routes."""

        app = FastAPI()

        @app.get("/users/{id}")
        @mcp_tool(name="get_user_info", description="Get user information")
        async def get_user(id: int):
            return {"id": id}

        @app.get("/hidden")
        @mcp_tool(hidden=True)
        async def hidden_route():
            return {"hidden": True}

        @app.get("/auto")
        async def auto_route():
            return {"auto": True}

        return app

    def test_custom_name_via_decorator(self, app_with_decorator):
        """Test custom tool name via decorator."""
        adapter = MCPAdapter(app_with_decorator)

        for path, method, handler, config in adapter.get_routes():
            if path == "/users/{id}":
                tool_info = adapter.introspect_route(path, method, handler, config)
                assert tool_info.name == "get_user_info"
                assert tool_info.description == "Get user information"
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

        assert "hidden_route" not in visible_tools
        assert "get_user_info" in visible_tools
        assert "get_auto" in visible_tools


class TestFastAPIExecution:
    """Test tool execution."""

    @pytest.fixture
    def app_for_execution(self):
        """Create app for execution testing."""
        app = FastAPI()

        @app.get("/users/{id}")
        async def get_user(id: int):
            return {"id": id, "name": "Test"}

        @app.get("/echo")
        async def echo(msg: str = "hello"):
            return {"message": msg}

        return app

    def test_sync_handler_execution(self, app_for_execution):
        """Test executing sync handler (though FastAPI routes are async)."""
        adapter = MCPAdapter(app_for_execution)

        for path, method, handler, config in adapter.get_routes():
            if path == "/echo":
                result = adapter.execute_tool(handler, {"msg": "test"})
                assert result == {"message": "test"}
                return

        pytest.fail("Route not found")

    def test_path_param_execution(self, app_for_execution):
        """Test executing with path parameters."""
        adapter = MCPAdapter(app_for_execution)

        for path, method, handler, config in adapter.get_routes():
            if path == "/users/{id}":
                result = adapter.execute_tool(handler, {"id": 42})
                assert result["id"] == 42
                assert result["name"] == "Test"
                return

        pytest.fail("Route not found")


class TestFastAPIEnum:
    """Test enum support."""

    @pytest.fixture
    def app_with_enum(self):
        """Create app with enum parameter."""
        from enum import Enum

        class Status(str, Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        app = FastAPI()

        @app.get("/items")
        async def get_items(status: Status = Status.ACTIVE):
            return {"status": status}

        return app

    def test_enum_schema(self, app_with_enum):
        """Test enum type in schema."""
        adapter = MCPAdapter(app_with_enum)

        for path, method, handler, config in adapter.get_routes():
            if path == "/items":
                tool_info = adapter.introspect_route(path, method, handler, config)
                props = tool_info.input_schema["properties"]
                assert "status" in props
                assert props["status"]["type"] == "string"
                assert "enum" in props["status"]
                return

        pytest.fail("Route not found")