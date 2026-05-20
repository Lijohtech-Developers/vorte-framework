# Routing & Versioning

Vorte extends FastAPI routing with API versioning, deprecation headers, and N+1 query optimization.

## Basic Routing

```python
from vorte import Vorte

app = Vorte(auto_load=True)

@app.get("/users")
async def list_users():
    return success_response(data=[...])

@app.post("/users")
async def create_user():
    return success_response(data={...}, status_code=201)

@app.put("/users/{user_id}")
async def update_user(user_id: int):
    return success_response(data={...})

@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    return success_response(status_code=204)
```

## VorteAPIRouter

Use `VorteAPIRouter` for modular route groups:

```python
from vorte.core.router import VorteAPIRouter

users = VorteAPIRouter(prefix="/users", tags=["users"])

@users.get("/")
async def list_users():
    return success_response(data=[...])

@users.get("/{user_id}")
async def get_user(user_id: int):
    return success_response(data={...})

app.include_router(users, prefix="/api/v1")
```

## API Versioning

### URL-based Versioning (default)

```python
from vorte.core.router import VorteAPIRouter

api = VorteAPIRouter()

@api.get("/users", version="v1")
async def list_users_v1():
    return success_response(data=[...])

@api.get("/users", version="v2")
async def list_users_v2():
    return success_response(data=[...], pagination={...})

app.include_router(api, prefix="/api")
# Routes: /api/v1/users and /api/v2/users
```

### Header-based Versioning

```python
from vorte.core.router import VersioningMiddleware

# Configure in app
app._versioning = VersioningMiddleware(
    default_version="v1",
    strategy="header"
)

# Client sends: API-Version: v2
```

### Default Version

Set via settings:

```env
VORTE_DEFAULT_VERSION=v2
```

Or programmatically:

```python
app.configure(default_version="v2")
```

## Route Deprecation

Mark routes as deprecated with sunset dates:

```python
@users.get(
    "/search",
    version="v1",
    deprecated_in="v1",
    removed_in="v2",
    sunset_date="2025-12-31",
)
async def search_v1():
    return success_response(data=[...])
```

This automatically adds response headers:

```http
Deprecation: true
Sunset: Wed, 31 Dec 2025 00:00:00 GMT
Link: </api/v2/search>; rel="successor-version"
```

## N+1 Query Optimization

VorteAPIRoute automatically inspects `response_model` for nested Pydantic models and infers SQLAlchemy relationships:

```python
from pydantic import BaseModel

class ProfileResponse(BaseModel):
    bio: str
    avatar: str

class UserResponse(BaseModel):
    name: str
    email: str
    profile: ProfileResponse  # Auto-detected relationship

# VorteAPIRoute infers "profile" relationship
# QueryPlanner adds selectinload(User.profile) automatically
@app.get("/users", response_model=list[UserResponse])
async def list_users():
    return await User.all()  # No N+1 queries!
```

### Manual Eager Loading

```python
from vorte import select_related

@select_related("posts", "posts.comments")
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return await User.get(user_id)
```

## Default Router Instance

A convenience router is exported as `router`:

```python
from vorte import router

@router.get("/status")
async def status():
    return {"status": "ok"}
```

## Route Inspection

```python
# Get all routes
routes = app.get_routes()
# Returns: [{"path": "/users", "methods": ["GET"], "name": "list_users"}, ...]

# Via CLI
# vorte routes

# Via dashboard API
# GET /_vorte/dashboard/routes
```

## WebSocket Routes

```python
@app.socket("/ws/chat")
async def chat_websocket(websocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Echo: {data}")
```
