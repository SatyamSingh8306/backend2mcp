"""backend2mcp CLI using typer."""

import importlib
from pathlib import Path

import typer

from backend2mcp.core.exceptions import AdapterConfigurationError

app = typer.Typer(
    name="backend2mcp",
    help="Convert Python web backends into MCP servers",
    add_completion=False,
)


@app.command()
def run(
    module_path: str = typer.Argument(
        ..., help="Module path to app object (e.g., 'app:app')"
    ),
    framework: str = typer.Option(
        None,
        "--framework",
        "-f",
        help="Framework (fastapi, flask, django). Auto-detected if not provided",
    ),
) -> None:
    """Run an MCP server from a Python web backend module."""
    typer.echo(f"Loading module from: {module_path}")

    # Parse module path
    if ":" not in module_path:
        raise AdapterConfigurationError(
            f"Invalid module path format. Use 'module:object' format. Got: {module_path}"
        )

    module_name, obj_name = module_path.rsplit(":", 1)

    # Import the module
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise AdapterConfigurationError(
            f"Failed to import module '{module_name}': {e}"
        ) from e

    # Get the object
    try:
        obj = getattr(module, obj_name)
    except AttributeError as e:
        raise AdapterConfigurationError(
            f"Failed to get '{obj_name}' from module '{module_name}': {e}"
        ) from e

    # Detect framework and create adapter
    adapter = _detect_and_create_adapter(obj, framework)

    if adapter is None:
        raise AdapterConfigurationError(
            f"Could not detect framework for object type: {type(obj)}"
        )

    typer.echo(f"Starting MCP server with {framework or 'auto-detected'} adapter...")
    adapter.run()


def _detect_and_create_adapter(obj: object, framework: str | None):
    """Detect framework and create appropriate adapter."""
    # Check for FastAPI
    if framework in (None, "fastapi"):
        try:
            from fastapi import FastAPI
            from backend2mcp.fastapi import MCPAdapter as FastAPIMCPAdapter

            if isinstance(obj, FastAPI):
                return FastAPIMCPAdapter(obj)
        except ImportError:
            pass

    # Check for Flask
    if framework in (None, "flask"):
        try:
            from flask import Flask
            from backend2mcp.flask import MCPAdapter as FlaskMCPAdapter

            if isinstance(obj, Flask):
                return FlaskMCPAdapter(obj)
        except ImportError:
            pass

    # Check for Django URLs
    if framework in (None, "django"):
        from backend2mcp.django import MCPAdapter as DjangoMCPAdapter

        if hasattr(obj, "__iter__") and not isinstance(obj, str):
            # Likely a urlpatterns list
            try:
                from django.urls import URLPattern

                first = next(iter(obj))
                if isinstance(first, URLPattern):
                    return DjangoMCPAdapter(urls=list(obj))
            except (StopIteration, TypeError):
                pass

        if isinstance(obj, list):
            return DjangoMCPAdapter(urls=obj)

    return None


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()