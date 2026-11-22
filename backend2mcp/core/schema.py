"""Schema conversion utilities.

Turns Python type hints, Pydantic models, dataclasses and framework path
parameters into JSON Schema fragments suitable for MCP ``inputSchema``.
"""

from __future__ import annotations

import collections.abc
import inspect
import json
import re
import types
from dataclasses import MISSING as DATACLASS_MISSING
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from pathlib import Path, PurePath
from typing import (
    Annotated,
    Any,
    Literal,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)
from uuid import UUID

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from backend2mcp.core.exceptions import SchemaConversionError

# Parameter names that are framework plumbing, not MCP tool arguments.
DEFAULT_EXCLUDED_PARAMS = frozenset(
    {"request", "self", "cls", "headers", "auth_context", "response"}
)

_PARAM_PATTERNS = (
    re.compile(r"\{(?P<name>[^{}]+)\}"),       # FastAPI / Starlette: {id}
    re.compile(r"<(?:(?P<conv>\w+):)?(?P<name>\w+)>"),  # Flask / Django: <int:id>
    re.compile(r":(?P<name>\w+)"),             # Bottle: :id
)


def _json_safe(value: Any) -> Any:
    """Make a default value safe to embed in a JSON schema."""
    if isinstance(value, Enum):
        return value.value
    if value is PydanticUndefined or value is inspect.Parameter.empty:
        return None
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)


def _basic_type(typ: Any) -> dict[str, Any] | None:
    """Map scalar Python types to JSON Schema."""
    if typ is str:
        return {"type": "string"}
    if typ is bool:
        return {"type": "boolean"}
    if typ is int:
        return {"type": "integer"}
    if typ is float:
        return {"type": "number"}
    if typ is bytes or typ is bytearray:
        return {"type": "string", "format": "binary"}
    if typ is datetime:
        return {"type": "string", "format": "date-time"}
    if typ is date:
        return {"type": "string", "format": "date"}
    if typ is time:
        return {"type": "string", "format": "time"}
    if typ is UUID:
        return {"type": "string", "format": "uuid"}
    if typ is Decimal:
        return {"type": "number"}
    if typ in (Path, PurePath) or (
        inspect.isclass(typ) and issubclass(typ, PurePath)
    ):
        return {"type": "string", "format": "path"}
    return None


def type_to_json_schema(
    typ: Any, field_name: str | None = None, _seen: frozenset[Any] | None = None
) -> dict[str, Any]:
    """Convert a Python type to a JSON Schema dictionary.

    Supports scalars, ``Optional``/unions (including PEP 604 ``|``),
    ``Literal``, Enums, Pydantic models, dataclasses, sequences, mappings,
    ``Annotated`` metadata and recursive model definitions.
    """
    if typ is None or typ is type(None) or typ is getattr(types, "NoneType", type(None)):
        return {"type": "null"}
    if typ is Any or typ is inspect.Parameter.empty:
        return {}

    seen = _seen or frozenset()
    origin = get_origin(typ)
    args = get_args(typ)

    # Annotated[T, ...] — unwrap and pull out descriptions.
    if origin is Annotated:
        if not args:
            return {}
        schema = type_to_json_schema(args[0], field_name, seen)
        for meta in args[1:]:
            description = getattr(meta, "description", None)
            if description:
                schema["description"] = description
        return schema

    # Literal["a", "b"] -> enum
    if origin is Literal:
        values = list(args)
        schema: dict[str, Any] = {"enum": values}
        sample = values[0] if values else None
        if isinstance(sample, bool):
            schema["type"] = "boolean"
        elif isinstance(sample, int):
            schema["type"] = "integer"
        elif isinstance(sample, float):
            schema["type"] = "number"
        elif isinstance(sample, str):
            schema["type"] = "string"
        return schema

    # Optional[T], Union[A, B], A | B
    if origin in (Union, types.UnionType):
        non_none = [arg for arg in args if arg is not type(None)]
        if not non_none:
            return {"type": "null"}
        if len(non_none) == 1:
            return type_to_json_schema(non_none[0], field_name, seen)
        return {"anyOf": [type_to_json_schema(arg, field_name, seen) for arg in non_none]}

    # Enums (checked before scalars because str-Enums subclass str).
    if inspect.isclass(typ) and issubclass(typ, Enum):
        values = [member.value for member in typ]
        sample = values[0] if values else None
        enum_type = "string"
        if isinstance(sample, bool):
            enum_type = "boolean"
        elif isinstance(sample, int):
            enum_type = "integer"
        elif isinstance(sample, float):
            enum_type = "number"
        return {"type": enum_type, "enum": values}

    # Pydantic models.
    if inspect.isclass(typ) and issubclass(typ, BaseModel):
        if typ in seen:
            return {"type": "object"}  # Recursive model — stop the cycle.
        nested = seen | {typ}
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, field_info in typ.model_fields.items():
            field_schema = type_to_json_schema(field_info.annotation, name, nested)
            description = getattr(field_info, "description", None)
            if description:
                field_schema["description"] = description
            if not field_info.is_required():
                default = field_info.default
                if default is not PydanticUndefined:
                    field_schema["default"] = _json_safe(default)
            properties[name] = field_schema
            if field_info.is_required():
                required.append(name)
        result: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            result["required"] = required
        return result

    # Dataclasses.
    if inspect.isclass(typ) and is_dataclass(typ):
        if typ in seen:
            return {"type": "object"}
        nested = seen | {typ}
        try:
            hints = get_type_hints(typ, include_extras=True)
        except Exception:
            hints = getattr(typ, "__annotations__", {})
        properties = {}
        required = []
        for field in dataclass_fields(typ):
            annotation = hints.get(field.name, field.type)
            field_schema = type_to_json_schema(annotation, field.name, nested)
            has_default = (
                field.default is not DATACLASS_MISSING or field.default_factory is not DATACLASS_MISSING
            )
            if field.default is not DATACLASS_MISSING and field.default_factory is DATACLASS_MISSING:
                field_schema["default"] = _json_safe(field.default)
            properties[field.name] = field_schema
            if not has_default:
                required.append(field.name)
        result = {"type": "object", "properties": properties}
        if required:
            result["required"] = required
        return result

    # Sequences and mappings.
    if origin in (
        list,
        set,
        frozenset,
        collections.abc.Sequence,
        collections.abc.MutableSequence,
        collections.abc.Set,
        collections.abc.MutableSet,
        collections.abc.Iterable,
    ):
        item_schema = type_to_json_schema(args[0], field_name, seen) if args else {}
        return {"type": "array", "items": item_schema}

    if origin in (
        dict,
        collections.abc.Mapping,
        collections.abc.MutableMapping,
    ):
        if len(args) > 1:
            return {
                "type": "object",
                "additionalProperties": type_to_json_schema(args[1], field_name, seen),
            }
        return {"type": "object", "additionalProperties": True}

    if origin is tuple:
        if args and args[-1] is Ellipsis:
            return {
                "type": "array",
                "items": type_to_json_schema(args[0], field_name, seen) if args[0] is not Ellipsis else {},
            }
        return {"type": "array", "items": {}}

    # Bare builtin containers without parameters.
    if typ in (list, set, frozenset):
        return {"type": "array", "items": {}}
    if typ is dict:
        return {"type": "object", "additionalProperties": True}
    if typ is tuple:
        return {"type": "array", "items": {}}

    # Scalars and typed aliases like `list[str]` are handled above.
    basic = _basic_type(typ)
    if basic is not None:
        return basic

    # Unknown types default to string (matches the original behaviour).
    return {"type": "string"}


def schema_from_path(path: str, overrides: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """Extract path parameter names from a framework route pattern.

    Recognises ``{id}``, ``<id>``, ``<int:id>`` and ``:id`` styles.  The
    resulting schema entries default to strings; ``overrides`` maps a
    parameter name to a JSON Schema type (e.g. ``{"id": "integer"}``).
    """
    overrides = overrides or {}
    params: dict[str, dict[str, Any]] = {}
    for pattern in _PARAM_PATTERNS:
        for match in pattern.finditer(path):
            name = match.group("name")
            json_type = overrides.get(name, "string")
            params[name] = {"type": json_type}
    return params


def extract_schema_from_signature(
    func: Any,
    additional_params: dict[str, Any] | None = None,
    path_params: dict[str, Any] | None = None,
    exclude: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    """Extract a JSON input schema from a callable's signature.

    Args:
        func: Callable to introspect.
        additional_params: Extra properties to merge in (e.g. body fields).
        path_params: Path parameter schemas that take precedence.
        exclude: Parameter names to ignore entirely.
    """
    excluded = DEFAULT_EXCLUDED_PARAMS | set(exclude or ())
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError) as exc:
        raise SchemaConversionError(f"Failed to inspect function signature: {exc}") from exc

    try:
        hints = get_type_hints(func, include_extras=True)
    except Exception:
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name in excluded:
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        if path_params and name in path_params:
            field_schema = dict(path_params[name])
        else:
            annotation = hints.get(name, param.annotation)
            if annotation is inspect.Parameter.empty:
                annotation = str
            field_schema = type_to_json_schema(annotation, name)

        if param.default is not inspect.Parameter.empty:
            field_schema["default"] = _json_safe(param.default)
        else:
            required.append(name)
        properties[name] = field_schema

    if path_params:
        for name, field_schema in path_params.items():
            if name not in properties:
                properties[name] = dict(field_schema)
                required.append(name)

    if additional_params:
        for name, field_schema in additional_params.items():
            properties[name] = field_schema
            if name not in required:
                required.append(name)

    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def route_to_description(method: str, path: str) -> str:
    """Generate a human-readable description for a route."""
    return f"{method.upper()} {path}"
