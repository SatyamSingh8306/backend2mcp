"""backend2mcp CLI using typer."""

from __future__ import annotations

import importlib
from typing import Any

import typer

from backend2mcp.core.exceptions import AdapterConfigurationError

app = typer.Typer(
    name="backend2mcp",
    help="Convert Python web backends into MCP servers",
    add_completion=False,
)

FRAMEWORKS = (
    "fastapi",
    "flask",
    "django",
    "starlette",
    "aiohttp",
    "sanic",
    "bottle",
    "quart",
)


@app.callback()
def _cli_root() -> None:
    """Convert Python web backends into MCP servers."""


def _load_object(module_path: str) -> Any:
    """Import ``module:object`` and return the object."""
    if ":" not in module_path:
        raise AdapterConfigurationError(
            f"Invalid module path format. Use 'module:object' format. Got: {module_path}"
        )
    module_name, obj_name = module_path.rsplit(":", 1)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise AdapterConfigurationError(f"Failed to import module '{module_name}': {exc}") from exc
    try:
        return getattr(module, obj_name)
    except AttributeError as exc:
        raise AdapterConfigurationError(
            f"Failed to get '{obj_name}' from module '{module_name}': {exc}"
        ) from exc


def _detect_and_create_adapter(obj: object, framework: str | None):
    """Detect the framework of ``obj`` and build the matching adapter.

    Framework packages are imported lazily so only the frameworks the user
    actually installed need to be present.
    """
    if framework is not None and framework.lower() not in FRAMEWORKS:
        raise AdapterConfigurationError(
            f"Unknown framework '{framework}'. Choose from: {', '.join(FRAMEWORKS)}"
        )
    framework = framework.lower() if framework else None

    checks = (
        ("fastapi", "fastapi", "FastAPI", "backend2mcp.fastapi"),
        ("flask", "flask", "Flask", "backend2mcp.flask"),
        ("starlette", "starlette.applications", "Starlette", "backend2mcp.starlette"),
        ("aiohttp", "aiohttp", "Application", "backend2mcp.aiohttp"),
        ("sanic", "sanic", "Sanic", "backend2mcp.sanic"),
        ("bottle", "bottle", "Bottle", "backend2mcp.bottle"),
        ("quart", "quart", "Quart", "backend2mcp.quart"),
    )

    for name, module_name, class_name, adapter_module in checks:
        if framework not in (None, name):
            continue
        try:
            framework_cls = getattr(importlib.import_module(module_name), class_name)
            adapter_cls = getattr(importlib.import_module(adapter_module), "MCPAdapter")
        except ImportError:
            continue
        if isinstance(obj, framework_cls):
            return adapter_cls(obj)

    if framework in (None, "django"):
        try:
            from backend2mcp.django import MCPAdapter as DjangoMCPAdapter
            from django.urls import URLPattern
        except ImportError:
            DjangoMCPAdapter = None  # type: ignore[assignment]
            URLPattern = None  # type: ignore[assignment]

        if DjangoMCPAdapter is not None:
            if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, dict)):
                items = list(obj)
                if items and URLPattern is not None and all(
                    isinstance(item, URLPattern) for item in items
                ):
                    return DjangoMCPAdapter(urls=items)
            if isinstance(obj, list):
                return DjangoMCPAdapter(urls=obj)

    return None


def _create_adapter(module_path: str, framework: str | None, name: str | None):
    """Load an app and create its adapter, with actionable errors."""
    typer.echo(f"Loading module from: {module_path}")
    obj = _load_object(module_path)
    adapter = _detect_and_create_adapter(obj, framework)
    if adapter is None:
        raise AdapterConfigurationError(
            f"Could not detect framework for object type: {type(obj).__name__}"
        )
    if name:
        adapter.server_name = name
    return adapter


@app.command()
def run(
    module_path: str = typer.Argument(..., help="Module path to app object (e.g. 'app:app')"),
    framework: str | None = typer.Option(
        None, "--framework", "-f", help=f"Framework ({', '.join(FRAMEWORKS)}). Auto-detected"
    ),
    name: str | None = typer.Option(None, "--name", "-n", help="MCP server name"),
) -> None:
    """Run an MCP server from a Python web backend module."""
    adapter = _create_adapter(module_path, framework, name)
    typer.echo(f"Starting MCP server with {adapter.server_name}...")
    adapter.run()


@app.command("list-tools")
def list_tools(
    module_path: str = typer.Argument(..., help="Module path to app object (e.g. 'app:app')"),
    framework: str | None = typer.Option(
        None, "--framework", "-f", help=f"Framework ({', '.join(FRAMEWORKS)}). Auto-detected"
    ),
) -> None:
    """List the MCP tools a backend would expose, without starting a server."""
    adapter = _create_adapter(module_path, framework, None)
    tools = []
    for path, method, handler, config in adapter.get_routes():
        tool = adapter.introspect_route(path, method, handler, config)
        if tool.hidden:
            continue
        props = ", ".join(tool.input_schema.get("properties", {})) or "-"
        tools.append((tool.name, tool.http_method, tool.route_path, props, tool.description))

    if not tools:
        typer.echo("No tools found.")
        return

    typer.echo(f"{len(tools)} tool(s) found:\n")
    for tool_name, method, path, props, description in tools:
        typer.echo(f"  {tool_name}")
        typer.echo(f"    {description}")
        typer.echo(f"    arguments: {props}")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
