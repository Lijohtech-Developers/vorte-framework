# Dependency Injection

Vorte includes a full dependency injection container with singleton, request, and transient scopes.

## Container Basics

```python
from vorte import Container

container = Container()

# Register a service as singleton (default)
container.register(UserService, singleton=True)

# Register with factory
container.register(DatabaseService, factory=lambda: DatabaseService(url="..."))

# Register a specific instance
container.register_instance(CacheService, my_cache_instance)

# Register as transient (new instance every resolution)
container.register(EmailService, transient=True)
```

## Resolution

```python
# Synchronous
service = container.resolve(UserService)

# Asynchronous
service = await container.aresolve(AsyncService)

# Check if registered
if container.has(UserService):
    service = container.resolve(UserService)

# Get all implementations
services = container.get_all(Handler)
```

## Scopes

### Singleton

One instance for the container's lifetime:

```python
container.register(DatabaseService, singleton=True)
db1 = container.resolve(DatabaseService)
db2 = container.resolve(DatabaseService)
assert db1 is db2  # Same instance
```

### Request

One instance per HTTP request:

```python
container.register(RequestContext, transient=False)
# Framework creates/destroys per-request instances automatically
```

### Transient

New instance every resolution:

```python
container.register(EmailService, transient=True)
e1 = container.resolve(EmailService)
e2 = container.resolve(EmailService)
assert e1 is not e2  # Different instances
```

## Eager Initialization

Build all singletons eagerly at startup:

```python
# Synchronous
container.build()

# Asynchronous (also resolves async factories)
await container.abuild()
```

## Child Containers

Create scoped child containers that delegate to a parent:

```python
parent = Container()
parent.register(UserService, singleton=True)

child = parent.create_child()
# child.resolve(UserService) delegates to parent
```

## Wire Decorator

Register services at import time using `@wire`:

```python
from vorte import wire

@wire(MyService, singleton=True)
class MyService:
    def __init__(self):
        self.data = []
```

This registers `MyService` with the global DI container when the module is imported.

## Route Injection

Use `Depends` for automatic injection in route handlers:

```python
from vorte import Depends

@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    service: UserService = Depends(UserService),
):
    user = service.get_user(user_id)
    return success_response(data=user)
```

## Inject Decorator

Mark any function for DI:

```python
from vorte import inject, Depends

@inject
def process_data(
    data: dict,
    service: UserService = Depends(UserService),
):
    return service.process(data)
```

## Container Management

```python
# Reset all singletons and instances
container.reset()

# Check registration
container.has(MyService)  # True/False

# Request scope lifecycle (used internally by framework)
container.setup_request_scope("request-123")
# ... handle request ...
container.teardown_request_scope("request-123")
```

## Global Container

Vorte uses a global container shared by all `Vorte` instances:

```python
app = Vorte()
container = app.container  # This is the global container
```

## Full Example

```python
from vorte import Vorte, wire, Depends, Container

# Define services
@wire(UserRepository, singleton=True)
class UserRepository:
    async def get_user(self, user_id: int):
        return {"id": user_id, "name": "Alice"}

@wire(EmailService, singleton=True)
class EmailService:
    async def send(self, to: str, subject: str):
        print(f"Sending email to {to}")

# Use in routes
app = Vorte()

@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    repo: UserRepository = Depends(UserRepository),
):
    user = await repo.get_user(user_id)
    return success_response(data=user)
```
