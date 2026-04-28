"""
Vorte Database Seeders
======================
Framework for populating databases with seed data during development
and testing. Seeders are ordered classes that insert reference data,
demo records, or test fixtures.

Usage::

    class SeedUsers(BaseSeeder):
        order = 1

        async def run(self, db: "QueryBuilder"):
            await db.create(User, {"email": "admin@vorte.dev", "name": "Admin"})

    # Run all seeders
    await seeder_manager.run_all()

    # Run a specific seeder
    await seeder_manager.run("SeedUsers")

    # Roll back a seeder
    await seeder_manager.rollback("SeedUsers")
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type

from vorte.modules.database.connection import ConnectionManager
from vorte.modules.database.query import QueryBuilder


# ---------------------------------------------------------------------------
# Base seeder
# ---------------------------------------------------------------------------

class BaseSeeder(ABC):
    """
    Abstract base class for all seeders.

    Subclass and implement :meth:`run` for seed logic, and optionally
    :meth:`rollback` for cleanup logic.

    Attributes:
        order: Execution order (lower runs first). Default 100.
        environment: Environments where this seeder should run
            (``"all"``, ``"development"``, ``"testing"``). Default ``"all"``.
    """

    order: int = 100
    environment: str = "all"  # "all", "development", "testing", "production"

    @abstractmethod
    async def run(self, db: "QueryBuilder") -> None:
        """
        Execute the seed logic.

        Args:
            db: QueryBuilder instance for database operations.
        """
        ...

    async def rollback(self, db: "QueryBuilder") -> None:
        """
        Undo the seed logic.

        Called when rolling back this seeder. Default is a no-op.
        Override to clean up inserted data.
        """
        pass


# ---------------------------------------------------------------------------
# Seeder registry
# ---------------------------------------------------------------------------

class SeederManager:
    """
    Discovers, registers, and executes seeders.

    Seeders are Python modules in the configured *seeders_dir* that
    contain classes subclassing :class:`BaseSeeder`.

    Args:
        connection: Database connection manager.
        seeders_dir: Directory path containing seeder modules.
    """

    def __init__(
        self,
        connection: ConnectionManager,
        *,
        seeders_dir: str = "database/seeders",
        environment: str = "development",
    ):
        self._connection = connection
        self._seeders_dir = Path(seeders_dir)
        self._environment = environment
        self._registry: Dict[str, Type[BaseSeeder]] = {}
        self._applied: Set[str] = set()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> List[Type[BaseSeeder]]:
        """
        Scan the seeders directory and register all seeder classes.

        Returns:
            List of discovered seeder classes sorted by ``order``.
        """
        self._registry.clear()

        if not self._seeders_dir.exists():
            return []

        for py_file in self._seeders_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            self._load_seeder_file(py_file)

        return self.get_ordered_seeders()

    def register(self, seeder_class: Type[BaseSeeder]) -> None:
        """
        Manually register a seeder class.

        Args:
            seeder_class: A class subclassing :class:`BaseSeeder`.
        """
        name = seeder_class.__name__
        self._registry[name] = seeder_class

    def _load_seeder_file(self, filepath: Path) -> None:
        """Load a seeder module from a file path."""
        try:
            spec = importlib.util.spec_from_file_location(
                f"_seeders_{filepath.stem}", filepath
            )
            if spec is None or spec.loader is None:
                return
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, BaseSeeder)
                    and attr is not BaseSeeder
                ):
                    self._registry[attr.__name__] = attr
        except Exception as exc:
            print(f"Warning: Failed to load seeder {filepath}: {exc}")

    def get_ordered_seeders(self) -> List[Type[BaseSeeder]]:
        """Return registered seeders sorted by ``order`` attribute."""
        return sorted(
            self._registry.values(),
            key=lambda cls: getattr(cls, "order", 100),
        )

    def get_seeder(self, name: str) -> Optional[Type[BaseSeeder]]:
        """Look up a registered seeder by class name."""
        return self._registry.get(name)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(
        self,
        name: Optional[str] = None,
        *,
        db: Optional[QueryBuilder] = None,
    ) -> Dict[str, Any]:
        """
        Run one or all seeders.

        Args:
            name: Specific seeder class name. If *None*, runs all seeders.
            db: Optional pre-built QueryBuilder. Created from *connection* if omitted.

        Returns:
            Dict with ``ran``, ``skipped``, and ``errors`` keys.
        """
        if db is None:
            db = QueryBuilder(self._connection)

        if name is not None:
            seeder_cls = self._registry.get(name)
            if seeder_cls is None:
                raise ValueError(f"Seeder '{name}' not found in registry.")
            seeders = [seeder_cls]
        else:
            seeders = self.get_ordered_seeders()

        result: Dict[str, Any] = {"ran": [], "skipped": [], "errors": []}

        for seeder_cls in seeders:
            seeder_name = seeder_cls.__name__

            # Skip if already applied
            if seeder_name in self._applied:
                result["skipped"].append(seeder_name)
                continue

            # Check environment
            env = getattr(seeder_cls, "environment", "all")
            if env not in ("all", self._environment):
                result["skipped"].append(seeder_name)
                continue

            try:
                instance = seeder_cls()
                await instance.run(db)
                self._applied.add(seeder_name)
                result["ran"].append(seeder_name)
            except Exception as exc:
                result["errors"].append(
                    {"seeder": seeder_name, "error": str(exc)}
                )

        return result

    async def run_all(self) -> Dict[str, Any]:
        """
        Discover all seeders and run them.

        Convenience method that calls :meth:`discover` then :meth:`run`.
        """
        self.discover()
        return await self.run()

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    async def rollback(
        self,
        name: str,
        *,
        db: Optional[QueryBuilder] = None,
    ) -> bool:
        """
        Roll back a specific seeder.

        Args:
            name: Seeder class name.
            db: Optional pre-built QueryBuilder.

        Returns:
            *True* if rollback succeeded.
        """
        if db is None:
            db = QueryBuilder(self._connection)

        seeder_cls = self._registry.get(name)
        if seeder_cls is None:
            raise ValueError(f"Seeder '{name}' not found in registry.")

        try:
            instance = seeder_cls()
            await instance.rollback(db)
            self._applied.discard(name)
            return True
        except Exception as exc:
            print(f"Error rolling back seeder '{name}': {exc}")
            return False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """
        Return the current seeder status.

        Returns:
            Dict with ``registered``, ``applied``, and ``pending`` lists.
        """
        all_names = set(self._registry.keys())
        return {
            "registered": sorted(all_names),
            "applied": sorted(self._applied),
            "pending": sorted(all_names - self._applied),
        }

    def reset(self) -> None:
        """Clear the applied set (does not affect the database)."""
        self._applied.clear()
