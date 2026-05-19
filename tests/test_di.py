import pytest
from vorte import Container, Depends, inject

class DatabaseService:
    def __init__(self):
        self.connected = True

class CacheService:
    def __init__(self):
        self.driver = "redis"

class OrderService:
    def __init__(self, db: DatabaseService, cache: CacheService):
        self.db = db
        self.cache = cache


@pytest.mark.asyncio
async def test_container_singleton_registration():
    """Test singleton registration and resolution."""
    container = Container()
    
    # Register singleton
    container.register(DatabaseService, singleton=True)
    assert container.has(DatabaseService) is True
    
    # Resolve first time
    db1 = container.resolve(DatabaseService)
    assert isinstance(db1, DatabaseService)
    assert db1.connected is True
    
    # Resolve second time (should return same instance)
    db2 = container.resolve(DatabaseService)
    assert db1 is db2


@pytest.mark.asyncio
async def test_container_transient_registration():
    """Test transient registration and resolution."""
    container = Container()
    
    # Register transient
    container.register(CacheService, transient=True)
    
    # Resolve first time
    cache1 = container.resolve(CacheService)
    assert isinstance(cache1, CacheService)
    
    # Resolve second time (should return a new instance)
    cache2 = container.resolve(CacheService)
    assert cache1 is not cache2


@pytest.mark.asyncio
async def test_container_instance_registration():
    """Test pre-created instance registration."""
    container = Container()
    
    existing_db = DatabaseService()
    container.register_instance(DatabaseService, existing_db)
    
    assert container.has(DatabaseService) is True
    resolved_db = container.resolve(DatabaseService)
    assert resolved_db is existing_db


@pytest.mark.asyncio
async def test_container_factory_registration():
    """Test custom factory function registration."""
    container = Container()
    
    def cache_factory():
        c = CacheService()
        c.driver = "custom_memory"
        return c
        
    container.register(CacheService, factory=cache_factory, singleton=True)
    
    cache = container.resolve(CacheService)
    assert cache.driver == "custom_memory"


@pytest.mark.asyncio
async def test_container_reset():
    """Test resetting singleton instances in container."""
    container = Container()
    container.register(DatabaseService, singleton=True)
    
    db1 = container.resolve(DatabaseService)
    container.reset()
    
    # After reset, resolving should return a new instance
    db2 = container.resolve(DatabaseService)
    assert db1 is not db2


@pytest.mark.asyncio
async def test_async_resolve():
    """Test async dependency resolution."""
    container = Container()
    
    async def async_db_factory():
        import asyncio
        await asyncio.sleep(0.01)
        return DatabaseService()
        
    container.register(DatabaseService, factory=async_db_factory, singleton=True)
    
    db = await container.aresolve(DatabaseService)
    assert isinstance(db, DatabaseService)
    assert db.connected is True


@pytest.mark.asyncio
async def test_child_container_delegation():
    """Test parent container delegation inside a child container."""
    parent = Container()
    parent.register(DatabaseService, singleton=True)
    
    child = parent.create_child()
    child.register(CacheService, singleton=True)
    
    # Child can resolve its own binding
    assert child.has(CacheService) is True
    cache = child.resolve(CacheService)
    assert isinstance(cache, CacheService)
    
    # Child can resolve parent's binding
    db = child.resolve(DatabaseService)
    assert isinstance(db, DatabaseService)
    
    # Resolving parent's binding from child returns the exact singleton instance in parent
    parent_db = parent.resolve(DatabaseService)
    assert db is parent_db


def test_di_decorators():
    """Test that Depends and @inject decorators set the expected attributes."""
    # Test Depends helper
    class MyDependency:
        pass
        
    dep_marker = Depends(MyDependency, name="test_dep")
    assert getattr(dep_marker, "_vorte_depends", False) is True
    assert getattr(dep_marker, "_vorte_depends_kwargs", {}) == {"name": "test_dep"}

    # Test @inject decorator
    @inject
    def sample_injected_function(db: DatabaseService = Depends(DatabaseService)):
        return db
        
    assert getattr(sample_injected_function, "_vorte_injected", False) is True
