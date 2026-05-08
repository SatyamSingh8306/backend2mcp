# backend2mcp

> Convert any Python web backend into a fully functional MCP (Model Context Protocol) server automatically, with near-zero developer boilerplate.

## What is this?

`backend2mcp` automatically exposes your existing Python web API routes as MCP tools. No HTTP servers, no proxies, no code generation—just import and run.

## Installation

Install the core package:

```bash
pip install backend2mcp
```

Install with framework support:

```bash
pip install backend2mcp[fastapi]      # FastAPI support
pip install backend2mcp[flask]         # Flask support
pip install backend2mcp[django]        # Django support
pip install backend2mcp[fastapi,flask] # Multiple frameworks
```

## Quickstart

### FastAPI

```python
from fastapi import FastAPI
from backend2mcp.fastapi import MCPAdapter

app = FastAPI()

@app.get("/users/{id}")
async def get_user(id: int):
    return {"id": id, "name": "Satyam"}

MCPAdapter(app).run()
```

### Flask

```python
from flask import Flask
from backend2mcp.flask import MCPAdapter

app = Flask(__name__)

@app.route("/users/<int:id>")
def get_user(id):
    return {"id": id, "name": "Satyam"}

MCPAdapter(app).run()
```

### Django

```python
from django.urls import path
from backend2mcp.django import MCPAdapter

urlpatterns = [
    path("users/<int:id>/", views.get_user),
]

MCPAdapter(urlpatterns=urlpatterns).run()
```

## CLI Usage

```bash
# Auto-detect framework
backend2mcp run app:app

# Explicit framework
backend2mcp run app:app --framework fastapi
backend2mcp run app:app --framework flask
backend2mcp run app:app --framework django
```

## Decorator Override

Customize tool behavior with `@mcp_tool`:

```python
from backend2mcp.fastapi import MCPAdapter, mcp_tool

app = FastAPI()

@app.get("/users/{id}")
@mcp_tool(
    name="get_user",
    description="Get a user by their ID",
    hidden=False
)
async def get_user(id: int):
    return {"id": id}
```

## Tool Naming

Tools are auto-named using a consistent convention:

| Route | Tool Name |
|-------|-----------|
| `GET /users/{id}` | `get_by_id` |
| `POST /search` | `post_search` |
| `PUT /users/{id}` | `put_by_id` |
| `DELETE /users/{id}` | `delete_by_id` |

## Architecture

```
backend2mcp/
├── core/              # Shared implementation
│   ├── adapter.py     # BaseAdapter abstract interface
│   ├── server.py      # MCP server implementation
│   ├── schema.py      # Schema conversion utilities
│   └── exceptions.py  # Structured exceptions
├── fastapi/           # FastAPI adapter
├── flask/             # Flask adapter
├── django/            # Django adapter
└── cli/               # Typer CLI
```

### Core Abstractions

- **`BaseAdapter`**: Abstract interface all framework adapters implement
- **`MCPServer`**: Handles MCP protocol using official `mcp` SDK
- **Tool Execution**: Direct handler invocation (no HTTP calls)
- **Schema Generation**: Pydantic-integrated JSON Schema extraction

## Writing a New Adapter

To add support for another framework:

1. Create `backend2mcp/framework/`
2. Implement `BaseAdapter` interface:
   - `get_routes()` - Extract all routes from the framework
   - `introspect_route()` - Convert a route to `ToolInfo`
   - `execute_tool()` - Call handler with resolved arguments
   - `build_tool_name()` - Generate MCP-safe tool names
3. Export `MCPAdapter` from the subpackage

```python
from backend2mcp.core.adapter import BaseAdapter, ToolInfo

class MCPAdapter(BaseAdapter):
    def get_routes(self) -> list[tuple]:
        # Your route extraction logic
        pass

    def introspect_route(self, path, method, handler, config) -> ToolInfo:
        # Your schema extraction logic
        pass

    def execute_tool(self, handler, arguments, context=None):
        # Your handler invocation logic
        pass

    def get_app(self):
        # Return underlying framework object
        pass

    def build_tool_name(self, http_method, path):
        # Your naming convention
        pass
```

## Roadmap

| Phase | Frameworks |
|-------|------------|
| Phase 1 (this release) | FastAPI, Flask, Django |
| Phase 2 | Express, NestJS, Fastify |
| Phase 3 | Spring Boot, Quarkus |
| Phase 4 | Gin, Fiber, Echo |

## License

MIT