# Application Lifecycle

The `Vorte` class is the central application instance that orchestrates all framework subsystems.

## Creating an Application

```python
from vorte import Vorte

# Minimal - auto-load all 21 modules
app = Vorte(auto_load=True)

# Custom - cherry-pick modules
app = Vorte()
app.register(AuthModule(), DatabaseModule(), AIModule())

# With configuration
app = Vorte(
    title="My API",
    description="A production API",
    version="2.0.0",
    auto_load=True,
    exclude_modules=["graphql"],
    dashboard=True,
)
```

## Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `settings` | `Settings` | `None` | Custom settings instance (auto-loaded from `.env` if `None`) |
| `title` | `str` | `None` | API title (for OpenAPI docs) |
| `description` | `str` | `None` | API description |
| `version` | `str` | `None` | API version |
| `auto_load` | `bool` | `False` | Auto-register all 21 built-in modules |
| `exclude_modules` | `list` | `None` | Module names to exclude when `auto_load=True` |
| `dashboard` | `bool` | `True` | Enable admin dashboard module |
| `**kwargs` | - | - | Additional FastAPI kwargs |

## Lifecycle Hooks

### Startup Hooks

```python
@app.on_startup
async def initialize_database():
    await db.connect()
    print("Database connected")

@app.on_startup
async def seed_data():
    await seed_initial_data()
```

### Shutdown Hooks

```python
@app.on_shutdown
async def close_database():
    await db.disconnect()
```

### Full Lifecycle Example

```python
app = Vorte(auto_load=True)

@app.on_startup
async def startup():
    # 1. Database connections are established
    # 2. Modules run their on_startup()
    # 3. Your startup hooks run
    # 4. TypeMirror scans routes for TypeScript generation
    print("Application started")

@app.on_shutdown
async def shutdown():
    # 1. Your shutdown hooks run
    # 2. Modules run their on_shutdown()
    # 3. Executor shuts down
    print("Application stopped")
```

## Route Registration

```python
# HTTP methods
@app.get("/users")
@app.post("/users")
@app.put("/users/{user_id}")
@app.patch("/users/{user_id}")
@app.delete("/users/{user_id}")

# WebSocket
@app.socket("/ws")

# Include router
app.include_router(api_router, prefix="/api/v2")

# Custom middleware
@app.middleware("http")
async def custom_middleware(request, call_next):
    response = await call_next(request)
    return response

# Exception handler
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return error_response(code="INVALID_VALUE", message=str(exc), status_code=400)
```

## Event System

```python
# Register event listener
@app.on("user.created")
async def on_user_created(data):
    await send_welcome_email(data["email"])

# Emit events
await app.emit("user.created", data={"email": "user@example.com"})
```

## Properties

```python
app.settings       # Settings instance
app.modules        # ModuleRegistry
app.container      # DI Container
app.executor       # VorteExecutor
app.type_mirror    # TypeMirror (TypeScript generation)
app.query_planner  # QueryPlanner (N+1 optimization)
app.events         # Dict of event listeners
```

## Utility Methods

```python
# Configure settings dynamically
app.configure(app_debug=True, cors_origins=["*"])

# Load config from a Python module
app.use_config("config.production")

# Get all registered routes
routes = app.get_routes()

# Get module health status
health = app.get_module_health()

# Add middleware
app.add_middleware(CustomMiddleware)

# Mount sub-application
app.mount("/docs", static_app)

# Record custom request metrics
app.record_request(
    path="/api/users",
    method="GET",
    status_code=200,
    latency_ms=12.5
)
```

## ASGI Interface

The Vorte app is a valid ASGI application:

```python
# Direct ASGI
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=8000)

# Via VorteEngine
from vorte import VorteEngine
engine = VorteEngine(app, host="0.0.0.0", port=8000, workers=4)
engine.run()
```

## Testing Helpers

For test environments, you can manually trigger lifecycle events:

```python
app = Vorte(auto_load=True)

# Manually trigger startup
await app._run_startup()

# Run tests...

# Manually trigger shutdown
await app._run_shutdown()
```
