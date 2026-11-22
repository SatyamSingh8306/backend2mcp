"""Tests for the additional framework adapters (Starlette, aiohttp, ...)."""

from __future__ import annotations

import pytest


class TestStarletteAdapter:
    @pytest.fixture
    def app(self):
        starlette = pytest.importorskip("starlette")
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def get_item(request):
            return JSONResponse({"id": request.path_params["item_id"]})

        async def create_item(request):
            payload = await request.json()
            return JSONResponse(payload)

        return Starlette(
            routes=[
                Route("/items/{item_id}", get_item, methods=["GET"]),
                Route("/items", create_item, methods=["POST"]),
            ]
        )

    def test_routes_and_names(self, app):
        from backend2mcp.starlette import MCPAdapter

        adapter = MCPAdapter(app)
        routes = adapter.get_routes()
        assert len(routes) == 2
        assert routes[0][0] == "/items/<item_id>"
        assert routes[0][1] == "GET"

        infos = [adapter.introspect_route(*route) for route in routes]
        assert infos[0].name == "get_by_item_id"
        assert infos[1].name == "post_items"
        assert "item_id" in infos[0].input_schema["properties"]

    def test_execution(self, app):
        from backend2mcp.starlette import MCPAdapter

        adapter = MCPAdapter(app)
        routes = adapter.get_routes()
        result = adapter.execute_tool(routes[0][2], {"item_id": "42"})
        assert result == {"id": "42"}


class TestAiohttpAdapter:
    @pytest.fixture
    def app(self):
        pytest.importorskip("aiohttp")
        from aiohttp import web

        async def get_item(request):
            return web.json_response({"id": request.match_info["item_id"]})

        app = web.Application()
        app.router.add_get("/items/{item_id}", get_item)
        app.router.add_post("/items", get_item)
        return app

    def test_routes_and_names(self, app):
        from backend2mcp.aiohttp import MCPAdapter

        adapter = MCPAdapter(app)
        routes = adapter.get_routes()
        assert len(routes) == 2
        assert routes[0][0] == "/items/<item_id>"
        assert routes[0][1] == "GET"

        infos = [adapter.introspect_route(*route) for route in routes]
        assert infos[0].name == "get_by_item_id"

    def test_execution(self, app):
        from backend2mcp.aiohttp import MCPAdapter

        adapter = MCPAdapter(app)
        routes = adapter.get_routes()
        result = adapter.execute_tool(routes[0][2], {"item_id": "7"})
        assert result == {"id": "7"}


class TestOptionalAdapters:
    @pytest.mark.parametrize(
        "framework,app_class",
        [
            ("sanic", "Sanic"),
            ("bottle", "Bottle"),
            ("quart", "Quart"),
        ],
    )
    def test_adapter_import_and_empty_app(self, framework: str, app_class: str):
        pytest.importorskip(framework)
        module = pytest.importorskip(f"backend2mcp.{framework}")
        app = getattr(pytest.importorskip(framework), app_class)()
        adapter = module.MCPAdapter(app)
        assert adapter.get_app() is app
        assert adapter.get_routes() == []
