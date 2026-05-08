"""Tests for Django adapter.

Note: These tests configure Django settings minimally.
"""

import pytest


class TestDjangoBasic:
    """Test basic Django adapter functionality."""

    @pytest.fixture
    def django_app(self, settings):
        """Create Django URL patterns for testing."""
        import django
        from django.conf import settings
        from django.urls import path

        settings.configure(
            DEBUG=True,
            SECRET_KEY="test-secret-key",
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
        )

        def get_user(request, id: int):
            return {"id": id, "name": "John"}

        def create_user(request):
            return {"status": "created"}

        def search(request):
            return {"results": []}

        urlpatterns = [
            path("users/<int:id>/", get_user),
            path("users/", create_user),
            path("search/", search),
        ]

        return urlpatterns

    def test_adapter_with_urlpatterns(self, django_app):
        """Test adapter can be created with URL patterns."""
        from backend2mcp.django import MCPAdapter

        adapter = MCPAdapter(urls=django_app)
        assert adapter.get_url_patterns() is not None

    def test_flatten_urlpatterns(self, django_app):
        """Test flattening of nested URL patterns."""
        from backend2mcp.django import MCPAdapter

        # Add nested patterns
        from django.urls import path, include

        nested_urlpatterns = [
            path("users/<int:id>/", include(list(django_app))),
        ]

        adapter = MCPAdapter(urls=nested_urlpatterns)
        patterns = adapter.get_url_patterns()

        assert len(patterns) > 0

    def test_build_tool_name(self):
        """Test tool name generation."""
        from backend2mcp.django import MCPAdapter

        adapter = MCPAdapter()

        # Simple path
        assert adapter.build_tool_name("GET", "/search/") == "get_search"

        # Path with converter
        assert adapter.build_tool_name("GET", "/users/<int:id>/") == "get_by_id"

        # POST with converter
        assert adapter.build_tool_name("POST", "/users/<int:id>/") == "post_by_id"


class TestDjangoDecorators:
    """Test @mcp_tool decorator for Django."""

    def test_custom_name_via_decorator(self):
        """Test custom tool name via decorator."""
        from backend2mcp.django import MCPAdapter, mcp_tool

        def dummy_view(request, id: int):
            return {"id": id}

        # Apply decorator
        decorated = mcp_tool(name="get_user_info", description="Get user")(dummy_view)

        from django.urls import path

        urlpatterns = [path("users/<int:id>/", decorated)]

        adapter = MCPAdapter(urls=urlpatterns)

        for path, method, handler, config in adapter.get_routes():
            if "users" in path:
                tool_info = adapter.introspect_route(path, method, handler, config)
                assert tool_info.name == "get_user_info"
                return

        pytest.fail("Route not found")


class TestDjangoExecution:
    """Test tool execution in Django."""

    def test_function_view_execution(self):
        """Test executing function-based view."""
        from backend2mcp.django import MCPAdapter

        def get_user(request, id: int):
            return {"id": id, "name": "Test"}

        from django.urls import path

        urlpatterns = [path("users/<int:id>/", get_user)]

        adapter = MCPAdapter(urls=urlpatterns)

        for path, method, handler, config in adapter.get_routes():
            if path == "/users/<id>/":
                result = adapter.execute_tool(handler, {"id": 42})
                assert result["id"] == 42
                return

        pytest.fail("Route not found")


class TestDjangoCBV:
    """Test class-based view support."""

    def test_class_based_view_introspection(self):
        """Test that CBVs are introspected properly."""
        from backend2mcp.django import MCPAdapter
        from django.http import JsonResponse
        from django.urls import path
        from django.views import View

        class UserView(View):
            def get(self, request, id: int):
                return JsonResponse({"id": id})

            def post(self, request, id: int):
                return JsonResponse({"id": id, "action": "created"})

        urlpatterns = [path("users/<int:id>/", UserView.as_view())]

        adapter = MCPAdapter(urls=urlpatterns)
        routes = adapter.get_routes()

        # Should have multiple routes (one per HTTP method)
        assert len(routes) >= 2