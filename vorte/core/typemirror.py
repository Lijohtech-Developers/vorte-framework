"""
Vorte TypeScript Type Mirror
==============================
Auto-generates TypeScript interface declarations from Pydantic models referenced
in VORTE route definitions. Prevents schema drift.

Blueprint reference: §5.2 Automated Type Mirroring
"""

from __future__ import annotations

import inspect
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type, get_args, get_origin
import typing

try:
    from pydantic import BaseModel
    _PYDANTIC = True
except ImportError:
    _PYDANTIC = False

_PY_TO_TS: Dict[str, str] = {
    "str": "string", "int": "number", "float": "number", "bool": "boolean",
    "bytes": "string", "Any": "unknown", "None": "null", "NoneType": "null",
    "datetime": "string", "date": "string", "time": "string", "UUID": "string",
    "Decimal": "number", "EmailStr": "string", "HttpUrl": "string", "AnyUrl": "string",
}


def _py_type_to_ts(annotation: Any, seen: Set[str]) -> str:
    if annotation is None or annotation is type(None):
        return "null"
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        base = " | ".join(_py_type_to_ts(a, seen) for a in non_none)
        if len(non_none) < len(args):
            base += " | null"
        return base
    if origin in (list, List):
        return f"{_py_type_to_ts(args[0], seen) if args else 'unknown'}[]"
    if origin is dict:
        k = _py_type_to_ts(args[0], seen) if args else "string"
        v = _py_type_to_ts(args[1], seen) if len(args) > 1 else "unknown"
        return f"Record<{k}, {v}>"
    if origin is tuple:
        return f"[{', '.join(_py_type_to_ts(a, seen) for a in args)}]" if args else "unknown[]"
    if _PYDANTIC and isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__
    if isinstance(annotation, type):
        return _PY_TO_TS.get(annotation.__name__, "unknown")
    if isinstance(annotation, str):
        return _PY_TO_TS.get(annotation, annotation)
    return "unknown"


def _model_to_interface(model: Type["BaseModel"]) -> str:
    lines: List[str] = [f"export interface {model.__name__} {{"]
    for field_name, field_info in model.model_fields.items():
        ts_type = _py_type_to_ts(field_info.annotation, set())
        optional = "" if field_info.is_required() else "?"
        if field_info.description:
            lines.append(f"  /** {field_info.description} */")
        lines.append(f"  {field_name}{optional}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def _collect_nested(model: Type["BaseModel"], seen: Set[str]) -> List[Type["BaseModel"]]:
    result: List[Type["BaseModel"]] = []
    if model.__name__ in seen:
        return result
    seen.add(model.__name__)
    for fi in model.model_fields.values():
        for ann in [fi.annotation, *get_args(fi.annotation)]:
            if _PYDANTIC and isinstance(ann, type) and issubclass(ann, BaseModel):
                result.extend(_collect_nested(ann, seen))
                if ann.__name__ not in {m.__name__ for m in result}:
                    result.append(ann)
    return result


class TypeMirror:
    """
    Generates TypeScript interface declarations from Pydantic models.

    Usage::

        mirror = TypeMirror.from_app(app)
        mirror.write("frontend/types/vorte.d.ts")

    Or via CLI::

        vorte manifest types --output frontend/types/vorte.d.ts
    """

    def __init__(self) -> None:
        self._models: List[Type["BaseModel"]] = []
        self._seen: Set[str] = set()

    def add_model(self, model: Type["BaseModel"]) -> "TypeMirror":
        nested = _collect_nested(model, set(self._seen))
        for m in nested:
            if m.__name__ not in self._seen:
                self._models.append(m)
                self._seen.add(m.__name__)
        if model.__name__ not in self._seen:
            self._models.append(model)
            self._seen.add(model.__name__)
        return self

    @classmethod
    def from_app(cls, app: Any) -> "TypeMirror":
        mirror = cls()
        if not _PYDANTIC:
            return mirror
        fastapi_app = getattr(app, "fastapi", app)
        for route in getattr(fastapi_app, "routes", []):
            rm = getattr(route, "response_model", None)
            if rm and isinstance(rm, type) and issubclass(rm, BaseModel):
                mirror.add_model(rm)
            endpoint = getattr(route, "endpoint", None)
            if endpoint:
                try:
                    for ann in inspect.get_annotations(endpoint).values():
                        if isinstance(ann, type) and issubclass(ann, BaseModel):
                            mirror.add_model(ann)
                except Exception:
                    pass
        return mirror

    def render(self) -> str:
        header = "/** VORTE Auto-Generated TypeScript Types\n * DO NOT EDIT — regenerate with `vorte manifest types`\n */\n\n"
        return header + "\n\n".join(_model_to_interface(m) for m in self._models) + "\n"

    def write(self, path: str | Path) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.render(), encoding="utf-8")

    @property
    def model_count(self) -> int:
        return len(self._models)

    @property
    def model_names(self) -> List[str]:
        return [m.__name__ for m in self._models]
