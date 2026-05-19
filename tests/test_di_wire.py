"""Tests for DI compile-time graph wiring — @wire and Container.build()."""
import pytest
from vorte.core.di import Container, wire, _wire_registry


class _MyService:
    def __init__(self):
        self.initialized = True

    def greet(self):
        return "hello from service"


class _AsyncService:
    async def fetch(self):
        return "async_data"


def test_container_build_materializes_singletons():
    container = Container()

    instance_created = []

    def factory():
        instance_created.append(True)
        return _MyService()

    container.register(_MyService, factory=factory, singleton=True)
    assert len(instance_created) == 0  # not yet materialized

    container.build()
    assert len(instance_created) == 1  # now materialized

    # Resolve again — should NOT call factory again (singleton)
    container.resolve(_MyService)
    assert len(instance_created) == 1


@pytest.mark.asyncio
async def test_container_abuild_resolves_async_factories():
    container = Container()

    async def async_factory():
        return _AsyncService()

    container.register(_AsyncService, factory=async_factory, singleton=True)
    await container.abuild()

    # Should be in instances
    instance = container._instances.get(_AsyncService)
    assert isinstance(instance, _AsyncService)


def test_container_build_skips_transient():
    """Transient bindings should not be materialized by build()."""
    container = Container()
    call_count = [0]

    def factory():
        call_count[0] += 1
        return _MyService()

    container.register(_MyService, factory=factory, transient=True)
    container.build()
    assert call_count[0] == 0  # transients not eagerly resolved


def test_container_build_ignores_failures_gracefully():
    """A broken factory during build should not crash the app."""
    container = Container()

    def bad_factory():
        raise RuntimeError("intentional failure")

    container.register(_MyService, factory=bad_factory, singleton=True)
    container.build()  # should not raise


def test_wire_decorator_registers_in_global_container():
    """@wire should pre-register the factory with the global DI container."""
    from vorte.core.di import _global_container

    class _WiredService:
        pass

    before = _global_container.has(_WiredService)

    @wire(_WiredService)
    class _WiredImpl(_WiredService):
        pass

    after = _global_container.has(_WiredService)
    assert after is True
    assert getattr(_WiredImpl, "_vorte_wired", False) is True
    assert getattr(_WiredImpl, "_vorte_wire_interface", None) is _WiredService


def test_wire_decorator_factory_function():
    """@wire should accept factory functions, not just classes."""
    from vorte.core.di import _global_container

    class _FactoryService:
        pass

    @wire(_FactoryService)
    def make_factory_service():
        return _FactoryService()

    assert _global_container.has(_FactoryService)
