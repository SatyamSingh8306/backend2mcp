"""Runtime helpers shared by all framework adapters."""

from __future__ import annotations

import asyncio
import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from backend2mcp.core.auth import AuthContext


def run_coroutine_sync(coro: Any) -> Any:
    """Run a coroutine to completion even when an event loop is already running.

    ``asyncio.run()`` raises ``RuntimeError`` inside a running loop, which is
    exactly the situation when MCP tool handlers are awaited by the SDK.  In
    that case the coroutine is executed on a dedicated worker thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class MockRequest:
    """A minimal request object for handlers that expect framework requests."""

    def __init__(self, arguments: dict[str, Any] | None = None, auth_context: AuthContext | None = None):
        headers = dict(auth_context.headers) if auth_context else {}
        args = dict(arguments or {})
        self.headers = headers
        self.query_params = args
        self.args = args
        self.GET = args
        self.params = args
        self.path_params = args
        self.match_info = args
        self.cookies: dict[str, str] = {}
        self.META = {
            f"HTTP_{key.upper().replace('-', '_')}": value for key, value in headers.items()
        }
        self.environ = dict(self.META)
        self.method = "GET"


def prepare_execution_arguments(
    handler: Callable[..., Any],
    arguments: dict[str, Any],
    auth_context: AuthContext | None = None,
) -> dict[str, Any]:
    """Filter MCP arguments and inject framework/auth plumbing when needed.

    Parameters such as ``request``, ``headers`` and ``auth_context`` are not
    exposed as MCP tool arguments (they are excluded from the input schema),
    but handlers may still expect them.  We inject lightweight equivalents so
    direct invocation behaves like a real request.
    """
    try:
        signature = inspect.signature(handler)
        parameter_names = set(signature.parameters)
        accepts_kwargs = any(
            param.kind is inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )
    except (TypeError, ValueError):
        parameter_names = set()
        accepts_kwargs = True

    exec_args = dict(arguments) if accepts_kwargs else {
        key: value for key, value in arguments.items() if key in parameter_names
    }

    if auth_context is not None:
        if "auth_context" in parameter_names:
            exec_args["auth_context"] = auth_context
        if "headers" in parameter_names:
            exec_args["headers"] = auth_context.headers

    # Framework handlers routinely expect a request object even when no auth
    # provider is configured.  Supply a lightweight stand-in so direct calls
    # behave like HTTP requests.
    if "request" in parameter_names:
        exec_args.setdefault("request", MockRequest(arguments, auth_context))

    return exec_args


def normalize_result(result: Any) -> Any:
    """Convert framework return values into JSON-serialisable data."""
    if result is None:
        return None

    # Pydantic models / arbitrary objects with model_dump.
    if hasattr(result, "model_dump") and callable(result.model_dump):
        try:
            return normalize_result(result.model_dump())
        except TypeError:
            pass

    # Flask responses.
    if hasattr(result, "get_json") and callable(result.get_json):
        try:
            payload = result.get_json()
            if payload is not None:
                return payload
        except Exception:
            pass

    # Django REST Framework responses.
    if hasattr(result, "data"):
        try:
            return normalize_result(result.data)
        except Exception:
            pass

    # Raw HTTP responses (Django HttpResponse, Starlette/aiohttp Response, ...).
    content: Any = None
    if hasattr(result, "content"):
        content = result.content
    elif hasattr(result, "body"):
        content = result.body
    if content is not None:
        if isinstance(content, (bytes, bytearray)):
            content = bytes(content).decode(errors="replace")
        if isinstance(content, str):
            try:
                return json.loads(content)
            except (TypeError, ValueError):
                return content
        return content

    if hasattr(result, "text") and callable(result.text):
        try:
            text = result.text()
        except Exception:
            text = None
        if isinstance(text, str):
            try:
                return json.loads(text)
            except (TypeError, ValueError):
                return text

    if isinstance(result, (dict, list, tuple, str, int, float, bool)):
        if isinstance(result, tuple):
            return list(result)
        return result

    return str(result)


def serialize_result(result: Any) -> str:
    """Serialise a tool result into the text payload of a MCP content block."""
    normalized = normalize_result(result)
    if isinstance(normalized, str):
        return normalized
    return json.dumps(normalized, default=str, ensure_ascii=False, indent=2)
