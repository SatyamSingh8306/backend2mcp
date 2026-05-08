"""Schema conversion utilities."""

import inspect
from enum import Enum
from typing import Any, get_type_hints

from pydantic import BaseModel

from backend2mcp.core.exceptions import SchemaConversionError


def type_to_json_schema(
    typ: Any, field_name: str | None = None
) -> dict[str, Any]:
    """Convert a Python type to JSON Schema.

    Args:
        typ: Python type to convert
        field_name: Optional field name for better error messages

    Returns:
        JSON Schema dictionary
    """
    origin = getattr(typ, "__origin__", None)
    args = getattr(typ, "__args__", ())

    # Handle None type
    if typ is type(None):
        return {"type": "null"}

    # Handle Pydantic models
    if inspect.isclass(typ) and issubclass(typ, BaseModel):
        schema = {"type": "object", "properties": {}}
        for field_name, field_info in typ.model_fields.items():
            field_schema = type_to_json_schema(field_info.annotation, field_name)
            if "default" in field_info and field_info.default is not inspect.Parameter.empty:
                field_schema["default"] = field_info.default
            schema["properties"][field_name] = field_schema
            if field_info.is_required():
                schema.setdefault("required", []).append(field_name)
        return schema

    # Handle generic types like List[str], Optional[str], etc.
    if origin is not None:
        # List[T]
        if origin is list:
            item_schema = type_to_json_schema(args[0]) if args else {}
            return {"type": "array", "items": item_schema}

        # Dict[K, V]
        if origin is dict:
            return {"type": "object", "additionalProperties": True}

        # Optional[T] = Union[T, None]
        if origin is type(None):
            return {"type": "null"}
        if getattr(typ, "__class__", None) == Union:
            non_none_types = [a for a in args if a is not type(None)]
            if len(non_none_types) == 1:
                return type_to_json_schema(non_none_types[0])

    # Handle Enum
    if inspect.isclass(typ) and issubclass(typ, Enum):
        return {"type": "string", "enum": [e.value for e in typ]}

    # Handle basic types
    type_map: dict[Any, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
    }

    for py_type, json_type in type_map.items():
        if typ is py_type:
            return {"type": json_type}

    # Default to string for unknown types
    return {"type": "string"}


def extract_schema_from_signature(
    func: Any, additional_params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Extract input schema from a function's signature.

    Args:
        func: Function to introspect
        additional_params: Additional params beyond signature (e.g., request bodies)

    Returns:
        Schema dictionary suitable for MCP inputSchema
    """
    try:
        sig = inspect.signature(func)
        hints = get_type_hints(func, include_extras=True)
    except Exception as e:
        raise SchemaConversionError(
            f"Failed to inspect function signature: {e}"
        ) from e

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        # Skip special parameters like request, self, etc.
        if param_name in ("request", "self", "cls"):
            continue

        annotation = hints.get(param_name, param.annotation)
        if annotation is param.empty:
            annotation = str

        schema = type_to_json_schema(annotation, param_name)

        if param.default is not inspect.Parameter.empty:
            schema["default"] = param.default
        else:
            required.append(param_name)

        properties[param_name] = schema

    # Add additional params (e.g., from request body)
    if additional_params:
        properties.update(additional_params)
        required.extend(additional_params.keys())

    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required

    return result


def route_to_description(method: str, path: str) -> str:
    """Generate a description for a route."""
    return f"{method.upper()} {path}"