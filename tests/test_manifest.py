"""Tests for vorte.cli.manifest — export, validate, types commands."""
import json
import sys
import pytest
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from vorte import Vorte


class ProductSchema(BaseModel):
    id: int
    name: str
    price: float
    description: Optional[str] = None


@pytest.fixture
def app_with_route(tmp_path):
    """Create a Vorte app with one route and register it in sys.modules."""
    app = Vorte(auto_load=False)

    @app.get("/products", response_model=ProductSchema, tags=["products"])
    async def list_products():
        """List all products."""
        return []

    # Make importable as test_manifest_app:app
    import types
    mod = types.ModuleType("test_manifest_app")
    mod.app = app
    sys.modules["test_manifest_app"] = mod
    yield app
    sys.modules.pop("test_manifest_app", None)


def test_manifest_export_writes_openapi(tmp_path, app_with_route):
    from vorte.cli.manifest import cmd_manifest_export
    out = tmp_path / "manifest.json"
    routes_out = tmp_path / "routes.json"

    cmd_manifest_export(
        app_import="test_manifest_app:app",
        output=str(out),
        routes_output=str(routes_out),
    )

    assert out.exists()
    schema = json.loads(out.read_text())
    assert "openapi" in schema
    assert "paths" in schema


def test_manifest_export_writes_route_tree(tmp_path, app_with_route):
    from vorte.cli.manifest import cmd_manifest_export
    out = tmp_path / "m.json"
    routes_out = tmp_path / "r.json"

    cmd_manifest_export(
        app_import="test_manifest_app:app",
        output=str(out),
        routes_output=str(routes_out),
    )

    assert routes_out.exists()
    routes = json.loads(routes_out.read_text())
    assert isinstance(routes, list)
    paths = [r["path"] for r in routes]
    assert any("/products" in p for p in paths)


def test_manifest_validate_no_drift(tmp_path, app_with_route):
    from vorte.cli.manifest import cmd_manifest_export, cmd_manifest_validate
    out = tmp_path / "manifest.json"
    routes_out = tmp_path / "routes.json"

    cmd_manifest_export(
        app_import="test_manifest_app:app",
        output=str(out),
        routes_output=str(routes_out),
    )
    # Validate against same app — no drift
    cmd_manifest_validate(
        app_import="test_manifest_app:app",
        manifest=str(out),
    )


def test_manifest_validate_missing_file(tmp_path):
    from vorte.cli.manifest import cmd_manifest_validate
    with pytest.raises(SystemExit):
        cmd_manifest_validate(
            app_import="test_manifest_app:app",
            manifest=str(tmp_path / "nonexistent.json"),
        )


def test_manifest_types_generates_ts(tmp_path, app_with_route):
    from vorte.cli.manifest import cmd_manifest_types
    out = tmp_path / "vorte.d.ts"

    cmd_manifest_types(
        app_import="test_manifest_app:app",
        output=str(out),
    )

    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "export interface" in content
    assert "ProductSchema" in content


def test_manifest_types_no_models(tmp_path):
    """CLI should report gracefully when no response_model is present."""
    app = Vorte(auto_load=False)

    @app.get("/ping")
    async def ping():
        return {}

    import types
    mod = types.ModuleType("test_manifest_empty")
    mod.app = app
    sys.modules["test_manifest_empty"] = mod

    from vorte.cli.manifest import cmd_manifest_types
    out = tmp_path / "empty.d.ts"
    # Should not crash, just print a message
    cmd_manifest_types(app_import="test_manifest_empty:app", output=str(out))

    sys.modules.pop("test_manifest_empty", None)
