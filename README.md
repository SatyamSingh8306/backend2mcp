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

## Authentication

`backend2mcp` provides flexible authentication support through pluggable `AuthProvider` classes.

### No Authentication (Default)

Zero config, no auth required:

```python
adapter = MCPAdapter(app)  # Works without auth
```

### Bearer Token Auth

```python
from backend2mcp.core import BearerAuthProvider

auth = BearerAuthProvider(
    token_header="Authorization",        # Header name
    token_prefix="Bearer",               # Token prefix
    validate_tokens=["secret1", "secr2"] # Optional whitelist
)
adapter = MCPAdapter(app, auth_provider=auth)
```

### API Key Auth

```python
from backend2mcp.core import APIKeyAuthProvider

auth = APIKeyAuthProvider(
    header_name="X-API-Key",     # Header name
    query_param="api_key",       # Query param name
    valid_keys=["key1", "key2"]  # Optional whitelist
)
adapter = MCPAdapter(app, auth_provider=auth)
```

### Custom Headers Injection

```python
from backend2mcp.core import HeaderInjectionAuthProvider

auth = HeaderInjectionAuthProvider(
    static_headers={
        "X-Custom-Header": "value",
        "Authorization": "Bearer static-token"
    }
)
adapter = MCPAdapter(app, auth_provider=auth)
```

### Combining Providers

```python
from backend2mcp.core import (
    BearerAuthProvider,
    APIKeyAuthProvider,
    combine_providers
)

auth = combine_providers(
    BearerAuthProvider(),
    APIKeyAuthProvider()
)
adapter = MCPAdapter(app, auth_provider=auth)
```

### Accessing Auth in Handlers

Auth context is injected into handlers:

```python
from backend2mcp.fastapi import MCPAdapter
from backend2mcp.core import BearerAuthProvider, AuthContext

app = FastAPI()
auth = BearerAuthProvider()

@app.get("/users/{id}")
async def get_user(id: int, auth_context: AuthContext = None):
    headers = auth_context.headers if auth_context else {}
    user = get_user_from_db(id, headers=headers)
    return user

adapter = MCPAdapter(app, auth_provider=auth)
```

## Architecture

```
backend2mcp/
├── core/              # Shared implementation
│   ├── adapter.py     # BaseAdapter abstract interface
│   ├── auth.py        # Auth providers (Bearer, API Key, etc.)
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
- **`AuthProvider` / `AuthContext`**: Pluggable authentication system
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