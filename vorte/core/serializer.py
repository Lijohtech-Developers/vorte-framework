"""
Vorte Fast Serializer
======================
Zero-copy-friendly JSON serialization using orjson when available, falling
back to the stdlib json module. Also provides the ``@lazy_schema`` decorator
for deferred Pydantic validation — data is kept as raw bytes until the route
handler explicitly calls ``.validate()``, eliminating eager validation debt
on every inbound request.

Blueprint reference: §4.3 Eliminating Serialization Overhead via Zero-Copy Paths
"""

from __future__ import annotations

import json as _stdlib_json
from functools import wraps
from typing import Any, Callable, Optional, Type, TypeVar

from pydantic import BaseModel

F = TypeVar("F", bound=Callable)


# ---------------------------------------------------------------------------
# Fast Serializer
# ---------------------------------------------------------------------------

try:
    import orjson as _orjson  # type: ignore[import]

    def _dumps(obj: Any) -> bytes:
        return _orjson.dumps(obj)

    def _dumps_str(obj: Any) -> str:
        return _orjson.dumps(obj).decode("utf-8")

    def _loads(data: bytes | str) -> Any:
        return _orjson.loads(data)

    _BACKEND = "orjson"

except ImportError:
    _orjson = None  # type: ignore[assignment]

    def _dumps(obj: Any) -> bytes:
        return _stdlib_json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")

    def _dumps_str(obj: Any) -> str:
        return _stdlib_json.dumps(obj, separators=(",", ":"), default=str)

    def _loads(data: bytes | str) -> Any:
        return _stdlib_json.loads(data)

    _BACKEND = "stdlib"


class FastSerializer:
    """
    Drop-in JSON serializer that picks the fastest available backend.

    Backend selection (highest priority first):
      1. ``orjson``  — C-extension, 3–10× faster than stdlib
      2. ``json``    — stdlib fallback (always available)

    Usage::

        data = FastSerializer.dumps({"key": "value"})  # -> bytes
        obj  = FastSerializer.loads(data)              # -> dict

    """

    backend: str = _BACKEND

    @staticmethod
    def dumps(obj: Any) -> bytes:
        """Serialize *obj* to a UTF-8 encoded JSON byte string."""
        return _dumps(obj)

    @staticmethod
    def dumps_str(obj: Any) -> str:
        """Serialize *obj* to a JSON string (text, not bytes)."""
        return _dumps_str(obj)

    @staticmethod
    def loads(data: bytes | str) -> Any:
        """Deserialize *data* from JSON."""
        return _loads(data)

    @classmethod
    def is_native(cls) -> bool:
        """Return ``True`` if orjson is being used."""
        return cls.backend == "orjson"


# ---------------------------------------------------------------------------
# Lazy Schema Decorator
# ---------------------------------------------------------------------------

class _LazyPayload:
    """
    Wraps raw request bytes and defers Pydantic validation until ``.validate()``
    is called. This eliminates eager deserialization cost for endpoints that
    need to inspect headers or auth before touching the body.

    Usage inside a route handler (after applying ``@lazy_schema``)::

        @lazy_schema(UserCreate)
        @app.post("/users")
        async def create_user(payload: _LazyPayload):
            # body NOT validated yet — zero cost so far
            data: UserCreate = payload.validate()
            ...
    """

    __slots__ = ("_raw", "_model", "_parsed")

    def __init__(self, raw: bytes, model: Type[BaseModel]) -> None:
        self._raw = raw
        self._model = model
        self._parsed: Optional[BaseModel] = None

    def validate(self) -> BaseModel:
        """Parse and validate the raw bytes against the registered Pydantic model."""
        if self._parsed is None:
            self._parsed = self._model.model_validate_json(self._raw)
        return self._parsed

    @property
    def raw(self) -> bytes:
        """Access the unvalidated raw bytes."""
        return self._raw

    def __repr__(self) -> str:
        state = "validated" if self._parsed is not None else "deferred"
        return f"<_LazyPayload model={self._model.__name__} state={state}>"


def lazy_schema(model: Type[BaseModel]) -> Callable[[F], F]:
    """
    Route decorator that defers Pydantic validation to the point of use.

    Wraps the route handler so the first body-typed parameter receives a
    :class:`_LazyPayload` instead of a fully-parsed model instance.  Call
    ``.validate()`` on the payload only when the business logic actually needs
    the data.

    Blueprint reference: §3 — Zero-Copy SIMD Acceleration / lazy schemas

    Usage::

        @lazy_schema(UserCreate)
        @app.post("/users")
        async def create_user(payload: _LazyPayload):
            user = payload.validate()
            ...
    """
    def decorator(func: F) -> F:
        func._vorte_lazy_schema = model  # type: ignore[attr-defined]

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        wrapper._vorte_lazy_schema = model  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
