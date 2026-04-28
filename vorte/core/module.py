"""
Vorte Module System
====================
Core module system for Vorte Framework. Every feature is a module
that can be registered, auto-discovered, and lazy-loaded.
"""

from __future__ import annotations

import asyncio
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from vorte.core.app import Vorte


class ModuleState(str, Enum):
    """Module lifecycle states."""
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    READY = "ready"
    FAILED = "failed"
    SHUTTING_DOWN = "shutting_down"
    SHUTDOWN = "shutdown"


class ModulePriority(int, Enum):
    """Module initialization priority (lower = earlier)."""
    CONFIG = 0
    DATABASE = 10
    CACHE = 20
    QUEUE = 30
    AUTH = 40
    SEARCH = 50
    MIDDLEWARE = 60
    ROUTES = 70
    AI = 80
    PAYMENTS = 90
    DASHBOARD = 100
    DEFAULT = 50


@dataclass
class ModuleMeta:
    """Metadata for a module."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    priority: ModulePriority = ModulePriority.DEFAULT
    dependencies: List[str] = field(default_factory=list)
    auto_discover: bool = True
    lazy_load: bool = False


class Module(ABC):
    """
    Base class for all Vorte modules.
    
    Every feature in Vorte (auth, database, AI, payments, etc.) is a Module.
    Modules are registered with the Vorte app and are auto-discovered.
    
    Usage:
        class MyModule(Module):
            meta = ModuleMeta(
                name="my_feature",
                description="My custom feature module",
                priority=ModulePriority.ROUTES,
            )
            
            async def on_startup(self):
                # Called when the app starts
                pass
            
            async def on_shutdown(self):
                # Called when the app shuts down
                pass
    """
    
    meta: ModuleMeta = ModuleMeta(name="base")
    state: ModuleState = ModuleState.REGISTERED
    app: Optional["Vorte"] = None
    
    def __init__(self, **config):
        self._config = config
        self._routers: List = []
        self._middleware: List = []
        self._event_handlers: Dict[str, Callable] = {}
        self._background_tasks: List = []
    
    @abstractmethod
    def register(self, app: "Vorte") -> None:
        """
        Register this module with the Vorte application.
        This is called during app initialization.
        """
        pass
    
    async def on_startup(self) -> None:
        """Called when the application starts."""
        pass
    
    async def on_shutdown(self) -> None:
        """Called when the application shuts down."""
        pass
    
    def add_router(self, router) -> None:
        """Add a router to be mounted by this module."""
        self._routers.append(router)
    
    def add_middleware(self, middleware) -> None:
        """Add middleware to be applied by this module."""
        self._middleware.append(middleware)
    
    def on(self, event_name: str) -> Callable:
        """Decorator to register an event handler."""
        def decorator(func: Callable) -> Callable:
            self._event_handlers[event_name] = func
            return func
        return decorator
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value for this module."""
        return self._config.get(key, default)
    
    def get_state(self) -> ModuleState:
        """Get the current module state."""
        return self.state
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if this module is healthy. Override for custom health checks."""
        return {
            "module": self.meta.name,
            "status": "healthy" if self.state == ModuleState.READY else self.state.value,
        }


class ModuleRegistry:
    """
    Registry for managing all registered modules.
    
    Handles module registration, lifecycle management, dependency resolution,
    and lazy loading.
    """
    
    def __init__(self):
        self._modules: Dict[str, Module] = {}
        self._priority_order: List[str] = []
    
    def register(self, module: Module) -> None:
        """Register a module."""
        if module.meta.name in self._modules:
            raise ValueError(f"Module '{module.meta.name}' is already registered.")
        
        self._modules[module.meta.name] = module
        self._update_priority_order()
    
    def get(self, name: str) -> Optional[Module]:
        """Get a registered module by name."""
        return self._modules.get(name)
    
    def get_all(self) -> Dict[str, Module]:
        """Get all registered modules."""
        return dict(self._modules)
    
    def get_by_state(self, state: ModuleState) -> List[Module]:
        """Get all modules in a specific state."""
        return [m for m in self._modules.values() if m.state == state]
    
    def _update_priority_order(self) -> None:
        """Update the priority order based on module priorities."""
        self._priority_order = sorted(
            self._modules.keys(),
            key=lambda name: self._modules[name].meta.priority.value,
        )
    
    def register_all(self, app: "Vorte") -> None:
        """Register all registered modules in priority order (Synchronous)."""
        # First pass: validate dependencies
        for name in self._priority_order:
            module = self._modules[name]
            for dep in module.meta.dependencies:
                if dep not in self._modules:
                    raise RuntimeError(
                        f"Module '{name}' depends on '{dep}', "
                        f"but '{dep}' is not registered."
                    )
        
        # Second pass: register
        for name in self._priority_order:
            module = self._modules[name]
            try:
                module.state = ModuleState.INITIALIZING
                module.app = app
                module.register(app)
                module.state = ModuleState.READY
            except Exception as e:
                module.state = ModuleState.FAILED
                raise RuntimeError(
                    f"Failed to register module '{name}': {e}"
                ) from e
    
    async def startup_all(self) -> None:
        """Call on_startup for all registered modules in priority order."""
        for name in self._priority_order:
            module = self._modules[name]
            if module.state == ModuleState.READY:
                try:
                    await module.on_startup()
                except Exception as e:
                    module.state = ModuleState.FAILED
                    raise RuntimeError(
                        f"Module '{name}' startup failed: {e}"
                    ) from e
    
    async def shutdown_all(self) -> None:
        """Call on_shutdown for all registered modules in reverse priority order."""
        for name in reversed(self._priority_order):
            module = self._modules[name]
            try:
                module.state = ModuleState.SHUTTING_DOWN
                await module.on_shutdown()
                module.state = ModuleState.SHUTDOWN
            except Exception as e:
                # Log but don't fail during shutdown
                print(f"Warning: Module '{name}' shutdown error: {e}")
    
    async def health_check_all(self) -> Dict[str, Any]:
        """Run health checks for all modules."""
        results = {}
        for name in self._priority_order:
            module = self._modules[name]
            try:
                results[name] = await module.health_check()
            except Exception as e:
                results[name] = {
                    "module": name,
                    "status": "unhealthy",
                    "error": str(e),
                }
        return results
    
    def list_modules(self) -> List[Dict[str, Any]]:
        """List all modules with their metadata and state."""
        return [
            {
                "name": module.meta.name,
                "version": module.meta.version,
                "description": module.meta.description,
                "state": module.state.value,
                "priority": module.meta.priority.value,
                "dependencies": module.meta.dependencies,
                "lazy_load": module.meta.lazy_load,
            }
            for module in self._modules.values()
        ]
