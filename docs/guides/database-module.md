# Database Module

SQLAlchemy async ORM with query planning, N+1 detection, and performance mode.

## Setup

```python
from vorte import DatabaseModule

app.register(DatabaseModule())
```

## Configuration

```env
VORTE_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mydb
# Or for development:
VORTE_DATABASE_URL=sqlite+aiosqlite:///./app.db
```

| Field | Default | Description |
|-------|---------|-------------|
| `url` | `sqlite+aiosqlite:///vorte.db` | Database URL |
| `pool_size` | `5` | Connection pool size |
| `max_overflow` | `10` | Max overflow connections |
| `echo` | `false` | Echo SQL statements |
| `read_replica_urls` | `[]` | Read replica URLs |

## N+1 Query Detection

```python
from vorte import N1Detector

detector = N1Detector(threshold=5)

# Track queries
detector.track("SELECT * FROM users WHERE id = 1")
detector.track("SELECT * FROM users WHERE id = 2")
# ...

if detector.is_n1():
    print(f"N+1 detected! {detector.query_count} queries")

detector.reset()  # Reset for next context
```

## Look-Ahead Query Planning

VorteAPIRoute automatically inspects `response_model` for nested Pydantic models and infers SQLAlchemy relationships:

```python
from pydantic import BaseModel

class ProfileResponse(BaseModel):
    bio: str

class UserResponse(BaseModel):
    name: str
    profile: ProfileResponse  # Relationship auto-detected

# QueryPlanner automatically adds selectinload(User.profile)
@app.get("/users", response_model=list[UserResponse])
async def list_users():
    return await User.all()
```

## select_related Decorator

Manually specify eager-loaded relationships:

```python
from vorte import select_related

@select_related("posts", "posts.comments")
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = await User.get(user_id)
    # user.posts and user.posts[*].comments are already loaded
    return success_response(data=user)
```

Multiple `@select_related` calls stack:

```python
@select_related("profile")
@select_related("posts")
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # Loads both profile and posts
    ...
```

## Performance Mode

Switch from ORM to raw SQL for maximum throughput:

```python
from vorte import performance_mode

@performance_mode
@app.get("/api/v1/users")
async def list_users_fast():
    # Uses raw SQL with FastSerializer.dumps
    # Bypasses ORM overhead entirely
    ...
```

`performance_mode` combines:
- Manual SQL stitching
- `FastSerializer.dumps` for serialization
- `@select_related` for automated eager loading

## PreparedSQLManager

```python
from vorte import PreparedSQLManager

manager = PreparedSQLManager()
# Manages prepared SQL statements for repeated execution
# Reduces query parsing overhead
```

## QueryPlanner API

```python
from vorte import QueryPlanner

planner = app.query_planner

# Get active relations for the current route
relations = planner.get_relations()

# Check if select_related was used
has_eager = planner.has_select_related()

# Apply eager loading to a SQLAlchemy query
query = planner.apply(query, model_class)

# Stats
stats = planner.stats
```

## Migrations

Vorte uses Alembic for database migrations:

```bash
vorte make:migration create_users_table   # Generate migration
vorte migrate                             # Run pending migrations
vorte migrate:rollback --step 1           # Rollback
vorte migrate:fresh --seed                # Drop all + re-migrate + seed
vorte migrate:status                      # Show status
```
