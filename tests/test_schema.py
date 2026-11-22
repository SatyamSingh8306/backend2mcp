"""Tests for the improved schema conversion utilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field

from backend2mcp.core.schema import (
    extract_schema_from_signature,
    schema_from_path,
    type_to_json_schema,
)
from backend2mcp.core.tool import build_tool_name, normalize_route_path


class Color(str, Enum):
    RED = "red"
    BLUE = "blue"


class Address(BaseModel):
    city: str
    zip_code: int = 0


class User(BaseModel):
    name: str
    age: int = Field(default=18, description="Age in years")
    tags: list[str] = []
    address: Address | None = None


@dataclass
class Point:
    x: int
    y: int = 0


class TestTypeConversion:
    def test_scalars(self):
        assert type_to_json_schema(str) == {"type": "string"}
        assert type_to_json_schema(int) == {"type": "integer"}
        assert type_to_json_schema(float) == {"type": "number"}
        assert type_to_json_schema(bool) == {"type": "boolean"}

    def test_optional_unwraps(self):
        assert type_to_json_schema(Optional[int]) == {"type": "integer"}
        assert type_to_json_schema(int | None) == {"type": "integer"}

    def test_union(self):
        assert type_to_json_schema(int | str) == {
            "anyOf": [{"type": "integer"}, {"type": "string"}]
        }

    def test_literal(self):
        assert type_to_json_schema(Literal["a", "b"]) == {
            "enum": ["a", "b"],
            "type": "string",
        }

    def test_enum(self):
        schema = type_to_json_schema(Color)
        assert schema["type"] == "string"
        assert schema["enum"] == ["red", "blue"]

    def test_containers(self):
        assert type_to_json_schema(list[int]) == {"type": "array", "items": {"type": "integer"}}
        assert type_to_json_schema(dict[str, int]) == {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        }

    def test_pydantic_model(self):
        schema = type_to_json_schema(User)
        props = schema["properties"]
        assert schema["required"] == ["name"]
        assert props["age"]["default"] == 18
        assert props["age"]["description"] == "Age in years"
        assert props["tags"]["items"] == {"type": "string"}
        assert props["address"]["type"] == "object"

    def test_dataclass(self):
        schema = type_to_json_schema(Point)
        assert schema["required"] == ["x"]
        assert schema["properties"]["y"]["default"] == 0

    def test_annotated(self):
        assert type_to_json_schema(Annotated[int, Field(description="an int")]) == {
            "type": "integer",
            "description": "an int",
        }

    def test_recursive_model(self):
        class Node(BaseModel):
            value: int
            child: "Node | None" = None

        schema = type_to_json_schema(Node)
        assert schema["properties"]["child"]["type"] == "object"


class TestSignatureExtraction:
    def test_defaults_and_types(self):
        def func(a: int, b: str = "x", c: bool = False):
            return a

        schema = extract_schema_from_signature(func)
        assert schema["required"] == ["a"]
        assert schema["properties"]["b"]["default"] == "x"
        assert schema["properties"]["c"] == {"type": "boolean", "default": False}

    def test_excluded_params(self):
        def func(request: Any, auth_context: Any, x: int):
            return x

        schema = extract_schema_from_signature(func)
        assert list(schema["properties"]) == ["x"]

    def test_path_params_override(self):
        def func(id: str, q: str = "all"):
            return id

        schema = extract_schema_from_signature(func, path_params={"id": {"type": "integer"}})
        assert schema["properties"]["id"]["type"] == "integer"
        assert schema["required"] == ["id"]


class TestPathHelpers:
    def test_schema_from_path(self):
        assert schema_from_path("/users/{id}/<int:age>/:slug") == {
            "id": {"type": "string"},
            "age": {"type": "string"},
            "slug": {"type": "string"},
        }

    def test_normalize(self):
        assert normalize_route_path("/users/{id}") == "/users/<id>"
        assert normalize_route_path("/users/<int:id>/") == "/users/<id>"
        assert normalize_route_path("/users/:id") == "/users/<id>"

    def test_tool_names(self):
        assert build_tool_name("GET", "/search") == "get_search"
        assert build_tool_name("GET", "/users/{id}") == "get_by_id"
        assert build_tool_name("POST", "/users/<int:id>") == "post_by_id"
        assert build_tool_name("DELETE", "/api/v1/users/:id") == "delete_by_id"
        assert build_tool_name("GET", "/users/{id}/posts") == "get_users_by_id_posts"
