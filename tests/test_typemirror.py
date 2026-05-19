"""Tests for vorte.core.typemirror — TypeScript type generation."""
import json
import pytest
from typing import List, Optional
from pydantic import BaseModel, Field
from vorte.core.typemirror import TypeMirror, _py_type_to_ts, _model_to_interface


# --- Fixture models ---

class Address(BaseModel):
    street: str
    city: str
    postcode: Optional[str] = None


class UserProfile(BaseModel):
    """User profile schema."""
    id: int
    name: str = Field(description="Full name of the user")
    email: str
    tags: List[str] = []
    address: Optional[Address] = None


# --- Unit tests ---

def test_primitive_type_mapping():
    seen = set()
    assert _py_type_to_ts(str, seen) == "string"
    assert _py_type_to_ts(int, seen) == "number"
    assert _py_type_to_ts(float, seen) == "number"
    assert _py_type_to_ts(bool, seen) == "boolean"


def test_optional_mapping():
    from typing import Optional
    seen = set()
    result = _py_type_to_ts(Optional[str], seen)
    assert "string" in result
    assert "null" in result


def test_list_mapping():
    from typing import List
    seen = set()
    result = _py_type_to_ts(List[str], seen)
    assert result == "string[]"


def test_dict_mapping():
    from typing import Dict
    seen = set()
    result = _py_type_to_ts(dict, seen)
    assert "Record" in result or result == "unknown"


def test_nested_model_reference():
    seen = set()
    result = _py_type_to_ts(Address, seen)
    assert result == "Address"


def test_model_to_interface_basic():
    ts = _model_to_interface(Address)
    assert "export interface Address {" in ts
    assert "street: string;" in ts
    assert "city: string;" in ts
    assert "postcode?" in ts or "postcode" in ts  # optional


def test_model_to_interface_with_description():
    ts = _model_to_interface(UserProfile)
    assert "/** Full name of the user */" in ts
    assert "name: string;" in ts


def test_type_mirror_add_model():
    mirror = TypeMirror()
    mirror.add_model(Address)
    assert "Address" in mirror.model_names
    assert mirror.model_count == 1


def test_type_mirror_nested_models_collected():
    mirror = TypeMirror()
    mirror.add_model(UserProfile)
    # Address should be auto-collected as a nested model
    assert "Address" in mirror.model_names
    assert "UserProfile" in mirror.model_names


def test_type_mirror_no_duplicates():
    mirror = TypeMirror()
    mirror.add_model(Address)
    mirror.add_model(Address)  # add twice
    assert mirror.model_names.count("Address") == 1


def test_type_mirror_render_produces_ts():
    mirror = TypeMirror()
    mirror.add_model(Address)
    ts = mirror.render()
    assert "export interface Address" in ts
    assert "VORTE Auto-Generated TypeScript Types" in ts


def test_type_mirror_from_app():
    from vorte import Vorte
    app = Vorte(auto_load=False)

    @app.get("/users", response_model=UserProfile)
    async def get_user():
        pass

    mirror = TypeMirror.from_app(app)
    assert mirror.model_count >= 1


def test_type_mirror_write(tmp_path):
    mirror = TypeMirror()
    mirror.add_model(Address)
    out = tmp_path / "vorte.d.ts"
    mirror.write(out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "export interface Address" in content
