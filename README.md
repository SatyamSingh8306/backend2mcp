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
pip install backend2mcp[starlette]     # Starlette support
pip install backend2mcp[aiohttp]       # aiohttp support
pip install backend2mcp[sanic]         # Sanic support
pip install backend2mcp[bottle]        # Bottle support
pip install backend2mcp[quart]         # Quart support
pip install backend2mcp[all]           # Every supported framework
```

Supported frameworks: FastAPI, Flask, Django, Starlette, aiohttp, Sanic,
Bottle and Quart. Every adapter has the same API: import `MCPAdapter` from
`backend2mcp.<framework>` and call `.run()`.

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

### Other frameworks

```python
# Starlette — from backend2mcp.starlette import MCPAdapter
# aiohttp   — from backend2mcp.aiohttp import MCPAdapter
# Sanic     — from backend2mcp.sanic import MCPAdapter
# Bottle    — from backend2mcp.bottle import MCPAdapter
# Quart     — from backend2mcp.quart import MCPAdapter

MCPAdapter(app).run()
```

All adapters accept an optional `auth_provider=` and `server_name=` argument.

## CLI Usage

```bash
# Auto-detect framework
backend2mcp run app:app

# Explicit framework
backend2mcp run app:app --framework fastapi
backend2mcp run app:app --framework flask
backend2mcp run app:app --framework django

# Custom MCP server name
backend2mcp run app:app --name my-api

# Inspect the tools that would be exposed (without starting the server)
backend2mcp list-tools app:app

# Also runnable as a module
python -m backend2mcp run app:app
```

`--framework` accepts: `fastapi`, `flask`, `django`, `starlette`, `aiohttp`,
`sanic`, `bottle`, `quart`.

## Decorator Override

Customize tool behavior with `@mcp_tool`:

```python
from backend2mcp.fastapi import MCPAdapter, mcp_tool

app = FastAPI()

@app.get("/users/{id}")
@mcp_tool(
    name="get_user",
    description="Get a user by their ID",
    hidden=False,
    tags=["users"],
    required_permissions=["read"],
)
async def get_user(id: int):
    return {"id": id}
```

`mcp_tool` options: `name`, `description`, `input_schema`, `hidden`, `tags`,
`required_permissions`. `required_permissions` are checked against the
`AuthContext` produced by your auth provider before a tool executes. The same
decorator is exported from every framework package and from `backend2mcp.core`.

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
│   ├── tool.py        # Shared tool naming + @mcp_tool decorator
│   ├── utils.py       # Async/result helpers
│   ├── simple.py      # Base class for lightweight adapters
│   └── exceptions.py  # Structured exceptions
├── fastapi/           # FastAPI adapter
├── flask/             # Flask adapter
├── django/            # Django adapter
├── starlette/         # Starlette adapter
├── aiohttp/           # aiohttp adapter
├── sanic/             # Sanic adapter
├── bottle/            # Bottle adapter
├── quart/             # Quart adapter
└── cli/               # Typer CLI
```

### Core Abstractions

- **`BaseAdapter`**: Abstract interface all framework adapters implement
- **`AuthProvider` / `AuthContext`**: Pluggable authentication system
- **`MCPServer`**: Handles MCP protocol using official `mcp` SDK
- **Tool Execution**: Direct handler invocation (no HTTP calls), sync and async
- **Schema Generation**: Pydantic/dataclass/type-hint JSON Schema extraction
- **Permission Checks**: `required_permissions` enforced before tool execution
- **Shared Naming**: One naming convention across every framework adapter

### MCP SDK compatibility

`backend2mcp` works with both MCP Python SDK 1.x and 2.x. The low-level `Server`
API changed in SDK 2.0: the `@server.list_tools()` / `@server.call_tool()`
decorators were replaced by `on_list_tools=` / `on_call_tool=` constructor
handlers with an `(ctx, params)` signature. The server layer detects the
installed API and registers the matching handlers, so no `<2` pin is needed.

## Writing a New Adapter

To add support for another framework:

1. Create `backend2mcp/framework/`
2. Implement `BaseAdapter` interface:
   - `get_routes()` - Extract all routes from the framework
   - `introspect_route()` - Convert a route to `ToolInfo`
   - `execute_tool()` - Call handler with resolved arguments
   - `build_tool_name()` - Generate MCP-safe tool names
3. Export `MCPAdapter` from the subpackage

For frameworks whose routes are simple ``(path, method, handler)`` tuples,
subclass `SimpleAdapter` instead — introspection, naming and execution come
for free:

```python
from backend2mcp.core.simple import SimpleAdapter

class MCPAdapter(SimpleAdapter):
    framework_name = "myframework"

    def get_routes(self):
        for route in self.get_app().routes:
            yield (route.path, route.method, route.handler, route)
```

For full control, subclass `BaseAdapter` and implement `get_routes()`,
`introspect_route()`, `execute_tool()`, `get_app()` and `build_tool_name()`.

## Roadmap

| Phase | Frameworks |
|-------|------------|
| Phase 1 (done) | FastAPI, Flask, Django |
| Phase 2 (done) | Starlette, aiohttp, Sanic, Bottle, Quart |
| Phase 3 | Express, NestJS, Fastify |
| Phase 4 | Spring Boot, Quarkus |
| Phase 5 | Gin, Fiber, Echo |

## License

MIT