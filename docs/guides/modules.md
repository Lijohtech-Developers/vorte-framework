# Module System

The module system is Vorte's plugin architecture. All features (Auth, AI, Database, etc.) are implemented as `Module` subclasses with priority-based initialization and dependency validation.

## Module Base Class

```python
from vorte.core.module import Module, ModuleMeta, ModulePriority, ModuleState

class CustomModule(Module):
    meta = ModuleMeta(
        name="custom",
        version="1.0.0",
        description="My custom module",
        priority=ModulePriority.DEFAULT,
        dependencies=["database"],      # Must be registered first
        auto_discover=True,
        lazy_load=False,
    )

    def register(self, app):
        """Called during app initialization. Register routes, middleware, etc."""
        @app.get("/custom")
        async def custom_route():
            return {"hello": "world"}

    async def on_startup(self):
        """Called after all modules are registered."""
        await self.initialize_resources()

    async def on_shutdown(self):
        """Called during graceful shutdown."""
        await self.cleanup_resources()

    async def health_check(self):
        """Return health status."""
        return {"module": "custom", "status": "healthy"}
```

## ModuleMeta Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | required | Unique module identifier |
| `version` | `str` | `"1.0.0"` | Module version |
| `description` | `str` | `""` | Human-readable description |
| `priority` | `ModulePriority` | `DEFAULT` | Initialization order (lower = earlier) |
| `dependencies` | `List[str]` | `[]` | Names of required modules |
| `auto_discover` | `bool` | `True` | Auto-discover routes |
| `lazy_load` | `bool` | `False` | Defer initialization until first use |

## ModulePriority Values

| Priority | Value | Use For |
|----------|-------|---------|
| `CONFIG` | 0 | Configuration modules |
| `DATABASE` | 10 | Database connections |
| `CACHE` | 20 | Cache layers |
| `QUEUE` | 30 | Job queues |
| `AUTH` | 40 | Authentication |
| `SEARCH` | 50 | Search engines |
| `DEFAULT` | 50 | General purpose |
| `MIDDLEWARE` | 60 | Middleware |
| `ROUTES` | 70 | Route handlers |
| `AI` | 80 | AI providers |
| `PAYMENTS` | 90 | Payment providers |
| `DASHBOARD` | 100 | Admin dashboard |

## ModuleState Lifecycle

```
REGISTERED -> INITIALIZING -> READY -> SHUTTING_DOWN -> SHUTDOWN
                                  \-> FAILED
```

| State | Description |
|-------|-------------|
| `REGISTERED` | Module added to registry |
| `INITIALIZING` | Running startup routine |
| `READY` | Fully operational |
| `FAILED` | Encountered an error |
| `SHUTTING_DOWN` | Running shutdown routine |
| `SHUTDOWN` | Shutdown complete |

## Module Registration

```python
from vorte import Vorte

app = Vorte()

# Register individual modules
app.register(AuthModule())
app.register(DatabaseModule())

# Register multiple at once
app.register(AuthModule(), DatabaseModule(), AIModule())

# Auto-load all built-in modules
app = Vorte(auto_load=True)

# Auto-load with exclusions
app = Vorte(auto_load=True, exclude_modules=["graphql", "sockets"])
```

## Module Events

Modules can listen for and emit events:

```python
class NotificationModule(Module):
    meta = ModuleMeta(name="notifications", ...)

    def register(self, app):
        self.on("user.created")(self.send_welcome_email)

    async def send_welcome_email(self, data):
        await email_service.send(to=data["email"], template="welcome")
```

## Module Configuration

Access module-specific configuration:

```python
class MyModule(Module):
    meta = ModuleMeta(name="my_module", ...)

    def register(self, app):
        # Access settings
        api_key = self.get_config("api_key")
        timeout = self.get_config("timeout", default=30)
```

## Health Checks

```python
# Single module
status = await my_module.health_check()
# Returns: {"module": "my_module", "status": "healthy"}

# All modules
health = app.get_module_health()
# Returns: {"my_module": {"status": "healthy"}, ...}

# Via HTTP
# GET /health - Returns 200 if all healthy, 503 if any degraded
```

## ModuleRegistry API

```python
registry = app.modules

# Get a specific module
auth = registry.get("auth")

# Get all modules
all_modules = registry.get_all()

# Get modules by state
ready_modules = registry.get_by_state(ModuleState.READY)

# List module metadata
module_list = registry.list_modules()

# Health check all modules
health_report = await registry.health_check_all()
```

## Dependency Validation

Dependencies are validated at registration time. If a required dependency is missing, an error is raised:

```python
class MyModule(Module):
    meta = ModuleMeta(
        name="my_module",
        dependencies=["database", "cache"],  # Both must be registered
    )

# This raises an error if "database" is not registered:
app.register(MyModule())
```

## Built-in Modules

Vorte includes 21 built-in modules. See their individual guides:

- [AI Module](ai-module.md)
- [Agents Module](agents-module.md)
- [Auth Module](auth-module.md)
- [Database Module](database-module.md)
- [Cache Module](cache-module.md)
- [Queue Module](queue-module.md)
- And more...
