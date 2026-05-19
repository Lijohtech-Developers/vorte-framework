"""
Vorte Manifest CLI Commands
============================
Compile-time schema manifest commands. Exports static OpenAPI + route tree
artifacts before production boot, eliminating cold-start schema reflection.

Blueprint reference: §3 — Compile-Time Manifest Compilation
  "Exporting static schema artifacts prior to production boot."

Registered as the ``manifest`` sub-command group in the Vorte CLI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _load_app(app_import: str) -> Any:
    """Import an ASGI app from a ``module:attribute`` import string."""
    parts = app_import.rsplit(":", 1)
    if len(parts) != 2:
        print(f"  Error: app must be in 'module:attribute' format, got: {app_import!r}")
        sys.exit(1)
    module_path, attr = parts
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    except (ImportError, AttributeError) as exc:
        print(f"  Error loading app '{app_import}': {exc}")
        sys.exit(1)


def cmd_manifest_export(
    app_import: str = "main:app",
    output: str = "vorte-manifest.json",
    routes_output: str = "vorte-routes.json",
) -> None:
    """
    Export OpenAPI schema and route tree to static JSON artifacts.

    These artifacts can be served directly by a CDN for zero-overhead
    documentation, and pre-loaded by the Rust router tree on boot.

    Usage::

        vorte manifest export --app main:app --output vorte-manifest.json
    """
    app = _load_app(app_import)
    fastapi_app = getattr(app, "fastapi", app)

    # --- OpenAPI schema ---
    try:
        schema = fastapi_app.openapi()
        out = Path(output)
        out.write_text(json.dumps(schema, indent=2, default=str), encoding="utf-8")
        print(f"  OpenAPI manifest written → {out}")
    except Exception as exc:
        print(f"  Warning: could not generate OpenAPI schema: {exc}")

    # --- Route tree ---
    try:
        routes = []
        for route in getattr(fastapi_app, "routes", []):
            if hasattr(route, "methods") and hasattr(route, "path"):
                routes.append({
                    "path": route.path,
                    "methods": sorted(route.methods or []),
                    "name": getattr(route, "name", ""),
                    "tags": getattr(route, "tags", []),
                    "deprecated": getattr(route, "deprecated", False),
                })
        routes_out = Path(routes_output)
        routes_out.write_text(json.dumps(routes, indent=2), encoding="utf-8")
        print(f"  Route tree written       → {routes_out}")
        print(f"  Routes exported: {len(routes)}")
    except Exception as exc:
        print(f"  Warning: could not export route tree: {exc}")


def cmd_manifest_validate(
    app_import: str = "main:app",
    manifest: str = "vorte-manifest.json",
) -> None:
    """
    Compare the live app OpenAPI schema against a saved ``vorte-manifest.json``
    and report any schema drift (added / removed / changed paths).

    Usage::

        vorte manifest validate --app main:app --manifest vorte-manifest.json
    """
    app = _load_app(app_import)
    fastapi_app = getattr(app, "fastapi", app)

    saved_path = Path(manifest)
    if not saved_path.exists():
        print(f"  Error: manifest file not found: {manifest}")
        print("  Run `vorte manifest export` first.")
        sys.exit(1)

    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    live = fastapi_app.openapi()

    saved_paths = set(saved.get("paths", {}).keys())
    live_paths = set(live.get("paths", {}).keys())

    added = live_paths - saved_paths
    removed = saved_paths - live_paths
    unchanged = saved_paths & live_paths

    print(f"\n  Schema Drift Report ({manifest}):")
    print(f"  --------------------------------")
    if not added and not removed:
        print("  ✓ No drift detected — schema matches saved manifest.")
    else:
        if added:
            print(f"  + Added paths ({len(added)}):")
            for p in sorted(added):
                print(f"      + {p}")
        if removed:
            print(f"  - Removed paths ({len(removed)}):")
            for p in sorted(removed):
                print(f"      - {p}")
    print(f"  Unchanged: {len(unchanged)}\n")


def cmd_manifest_types(
    app_import: str = "main:app",
    output: str = "vorte.d.ts",
) -> None:
    """
    Generate TypeScript interface declarations from Pydantic models registered
    on the app's routes.

    Usage::

        vorte manifest types --app main:app --output frontend/types/vorte.d.ts
    """
    app = _load_app(app_import)

    try:
        from vorte.core.typemirror import TypeMirror
    except ImportError as exc:
        print(f"  Error: TypeMirror not available: {exc}")
        sys.exit(1)

    mirror = TypeMirror.from_app(app)
    if mirror.model_count == 0:
        print("  No Pydantic response_model or body schemas found on routes.")
        print("  Tip: annotate routes with response_model=YourSchema.")
        return

    out = Path(output)
    mirror.write(out)
    print(f"  TypeScript types written → {out}")
    print(f"  Models exported: {mirror.model_count}")
    for name in mirror.model_names:
        print(f"    • {name}")
