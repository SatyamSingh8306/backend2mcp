"""Shared tool naming and decorator helpers."""

from __future__ import annotations

import re
from typing import Any, Callable

# Route parameter syntaxes used by the supported frameworks.
_BRACE_PARAM = re.compile(r"^\{(?P<name>[^{}]+)\}$")
_ANGLE_PARAM = re.compile(r"^<(?:(?P<conv>[\w.]+(?:\([^>]*\))?):)?(?P<name>\w+)>$")
_COLON_PARAM = re.compile(r"^:(?P<name>\w+)$")


def sanitize_name(value: str) -> str:
    """Lowercase and keep only ``a-z0-9_`` characters."""
    return re.sub(r"[^a-z0-9_]", "", value.lower())


def parse_path_parameter(segment: str) -> str | None:
    """Return the parameter name if a path segment is a placeholder."""
    for pattern in (_BRACE_PARAM, _ANGLE_PARAM, _COLON_PARAM):
        match = pattern.match(segment)
        if match:
            return match.group("name")
    return None


def normalize_route_path(path: str) -> str:
    """Normalise framework path syntax to ``<name>`` placeholders.

    ``/users/{id}``, ``/users/<int:id>`` and ``/users/:id`` all become
    ``/users/<id>``.  This keeps tool names and schemas consistent across
    adapters.
    """
    segments = []
    for segment in path.strip("/").split("/"):
        if not segment:
            continue
        param = parse_path_parameter(segment)
        segments.append(f"<{param}>" if param else segment)
    return "/" + "/".join(segments) if segments else "/"


def build_tool_name(http_method: str, path: str) -> str:
    """Build a deterministic, MCP-safe name from an HTTP method and path.

    The convention documented in the README is used: when a route ends with
    a path parameter the static prefix is dropped, e.g. ``GET /users/{id}``
    becomes ``get_by_id``.  Otherwise every static segment is kept, e.g.
    ``POST /search`` becomes ``post_search``.
    """
    parts: list[str] = [http_method.lower()]
    ends_with_param = False

    for segment in path.strip("/").split("/"):
        if not segment:
            continue
        param = parse_path_parameter(segment)
        if param:
            parts.append(f"by_{sanitize_name(param)}")
            ends_with_param = True
        else:
            parts.append(sanitize_name(segment))
            ends_with_param = False

    if ends_with_param:
        # Keep the HTTP method prefix, drop static path segments.
        parts = parts[:1] + [part for part in parts[1:] if part.startswith("by_")]

    tool_name = "_".join(part for part in parts if part)
    if tool_name and tool_name[0].isdigit():
        tool_name = f"_{tool_name}"
    return tool_name or "root"


def mcp_tool(
    name: str | None = None,
    description: str | None = None,
    input_schema: dict[str, Any] | None = None,
    hidden: bool = False,
    tags: list[str] | None = None,
    required_permissions: list[str] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Customise how a route is exposed as an MCP tool.

    Works with every supported framework — import it from the framework
    package (``backend2mcp.fastapi``, ``backend2mcp.flask``, ...) or from
    ``backend2mcp.core``.

    Args:
        name: Override the auto-generated tool name.
        description: Override the auto-generated description.
        input_schema: Override the discovered JSON input schema.
        hidden: Exclude the route from ``tools/list`` entirely.
        tags: Arbitrary labels for filtering/organising tools.
        required_permissions: Permissions checked before tool execution.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__mcp_tool__ = {  # type: ignore[attr-defined]
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "hidden": hidden,
            "tags": list(tags or []),
            "required_permissions": list(required_permissions or []),
        }
        return func

    return decorator
