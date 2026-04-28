"""
Vorte Dependency Injection Container
=====================================
Lightweight, async-aware dependency injection container with lifecycle management.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, TypeVar, Union

T = TypeVar("T")


class SingletonScope:
    """One instance per container lifetime."""
    _instances: Dict[str, Any] = {}

    def get(self, key: str, factory: Callable) -> Any:
        if key not in self._instances:
            self._instances[key] = factory()
        return self._instances[key]

    def reset(self):
        self._instances.clear()


class RequestScope:
    """One instance per request."""
    def __init__(self):
        self._instances: Dict[str, Any] = {}

    def get(self, key: str, factory: Callable) -> Any:
        if key not in self._instances:
            self._instances[key] = factory()
        return self._instances[key]

    def reset(self):
        self._instances.clear()


class TransientScope:
    """New instance every time."""
    def get(self, key: str, factory: Callable) -> Any:
        return factory()


@dataclass
class Binding:
    """A dependency binding."""
    factory: Callable
    scope: Union[str, object] = "singleton"
    interface: Optional[Type] = None
    is_async: bool = False


class Container:
    """
    Vorte's dependency injection container.
    
    Usage:
        container = Container()
        container.register(DatabaseService, singleton=True)
        container.register(EmailService, singleton=True)
        
        db = container.resolve(DatabaseService)
    """

    def __init__(self, parent: Optional["Container"] = None):
        self._bindings: Dict[Type, Binding] = {}
        self._instances: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._parent = parent
        self._request_scopes: Dict[int, RequestScope] = {}
        self._singleton_scope = SingletonScope()

    def register(
        self,
        interface_or_factory: Union[Type, Callable],
        implementation: Optional[Type] = None,
        *,
        singleton: bool = True,
        transient: bool = False,
        factory: Optional[Callable] = None,
        name: Optional[str] = None,
    ) -> None:
        """Register a dependency binding."""
        if factory:
            factory_fn = factory
        elif implementation:
            factory_fn = implementation
        elif callable(interface_or_factory) and not isinstance(interface_or_factory, type):
            factory_fn = interface_or_factory
        else:
            factory_fn = interface_or_factory

        if isinstance(interface_or_factory, type) and not factory:
            interface = interface_or_factory
        else:
            interface = implementation or interface_or_factory

        is_async = inspect.iscoroutinefunction(factory_fn) or (
            hasattr(factory_fn, "__call__") and inspect.iscoroutinefunction(factory_fn.__call__)
        )

        if transient:
            scope = TransientScope()
        elif singleton:
            scope = self._singleton_scope
        else:
            scope = TransientScope()

        binding = Binding(
            factory=factory_fn,
            scope=scope,
            interface=interface,
            is_async=is_async,
        )

        key = name or (interface if isinstance(interface, type) else factory_fn)
        self._bindings[key] = binding

        # Also bind by type if it's a class
        if isinstance(interface, type):
            self._bindings[interface] = binding

    def register_instance(self, interface: Type, instance: Any) -> None:
        """Register a pre-created instance."""
        self._instances[interface] = instance

    def resolve(self, interface: Type, **kwargs) -> Any:
        """Resolve a dependency."""
        # Check for pre-registered instance
        if interface in self._instances:
            return self._instances[interface]

        # Check bindings
        if interface in self._bindings:
            binding = self._bindings[interface]
            if isinstance(binding.scope, SingletonScope):
                return binding.scope.get(str(interface), binding.factory)
            elif isinstance(binding.scope, TransientScope):
                return binding.scope.get(str(interface), binding.factory)
            elif isinstance(binding.scope, RequestScope):
                return binding.scope.get(str(interface), binding.factory)

        # Check parent container
        if self._parent:
            return self._parent.resolve(interface, **kwargs)

        raise KeyError(f"No binding found for {interface}")

    async def aresolve(self, interface: Type, **kwargs) -> Any:
        """Async resolve a dependency."""
        if interface in self._instances:
            return self._instances[interface]

        if interface in self._bindings:
            binding = self._bindings[interface]
            if binding.is_async:
                instance = await binding.factory(**kwargs)
            else:
                instance = binding.factory(**kwargs)
            if isinstance(binding.scope, SingletonScope):
                self._instances[interface] = instance
            return instance

        if self._parent:
            return await self._parent.aresolve(interface, **kwargs)

        raise KeyError(f"No binding found for {interface}")

    def has(self, interface: Type) -> bool:
        """Check if a binding exists."""
        return interface in self._bindings or interface in self._instances

    def get_all(self, interface: Type) -> List[Any]:
        """Get all bindings for a given interface."""
        results = []
        for key, binding in self._bindings.items():
            if binding.interface == interface or key == interface:
                results.append(binding.factory())
        return results

    def reset(self):
        """Reset all singleton instances."""
        self._singleton_scope.reset()
        self._instances.clear()

    def create_child(self) -> "Container":
        """Create a child container for request scoping."""
        return Container(parent=self)

    def setup_request_scope(self, request_id: int) -> RequestScope:
        """Setup request-scoped dependencies."""
        scope = RequestScope()
        self._request_scopes[request_id] = scope
        return scope

    def teardown_request_scope(self, request_id: int):
        """Teardown request-scoped dependencies."""
        if request_id in self._request_scopes:
            self._request_scopes[request_id].reset()
            del self._request_scopes[request_id]


# Global container
_global_container = Container()


def Depends(dependency: Type, **kwargs):
    """Mark a parameter as a dependency to be injected.
    
    Usage:
        @router.get('/users')
        async def get_users(db: DatabaseService = Depends(DatabaseService)):
            ...
    """
    dependency._vorte_depends = True
    dependency._vorte_depends_kwargs = kwargs
    return dependency


def inject(func: Callable) -> Callable:
    """Decorator to enable dependency injection on a function.
    
    Usage:
        @inject
        async def my_service(db: DatabaseService = Depends(DatabaseService)):
            ...
    """
    func._vorte_injected = True
    return func
