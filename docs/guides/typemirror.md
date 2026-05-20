# TypeScript Generation (TypeMirror)

TypeMirror auto-generates TypeScript interfaces from Pydantic models found in your route definitions.

## How It Works

At startup, TypeMirror scans all registered FastAPI routes for:
1. `response_model` parameter on route decorators
2. Return type annotations on endpoint functions
3. Nested Pydantic models referenced by those models

It then generates a complete TypeScript declaration file.

## Usage

### Automatic (at startup)

TypeMirror is built automatically when the Vorte app starts:

```python
from vorte import Vorte

app = Vorte(auto_load=True)
# TypeMirror scans all routes and collects Pydantic models
# at startup via TypeMirror.from_app(app)
```

### Manual

```python
from vorte import TypeMirror
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str
    age: int | None = None

class UserList(BaseModel):
    users: list[User]
    total: int

mirror = TypeMirror()
mirror.add_model(UserList)

# Generate TypeScript
ts_code = mirror.render()
print(ts_code)
```

Output:

```typescript
export interface User {
  name: string;
  email: string;
  age?: number;
}

export interface UserList {
  users: User[];
  total: number;
}
```

### Write to File

```python
mirror.write("types/api.d.ts")
```

## Type Mappings

| Python Type | TypeScript Type |
|-------------|----------------|
| `str` | `string` |
| `int` | `number` |
| `float` | `number` |
| `bool` | `boolean` |
| `list[T]` | `T[]` |
| `List[T]` | `T[]` |
| `dict[K, V]` | `Record<K, V>` |
| `Dict[K, V]` | `Record<K, V>` |
| `tuple[A, B]` | `[A, B]` |
| `Optional[T]` | `T \| null` |
| `Union[A, B]` | `A \| B` |
| `datetime` | `string` |
| `date` | `string` |
| `UUID` | `string` |
| `Decimal` | `number` |
| Pydantic Model | Referenced interface |

## Nested Models

TypeMirror automatically collects nested models:

```python
class Address(BaseModel):
    street: str
    city: str

class Company(BaseModel):
    name: str
    address: Address  # Auto-collected

class User(BaseModel):
    name: str
    company: Company  # Auto-collected with nested Address

mirror = TypeMirror()
mirror.add_model(User)
# Generates interfaces for User, Company, and Address
```

## from_app

```python
mirror = TypeMirror.from_app(app)
# Scans all routes:
# - @app.get("/users", response_model=list[User])
# - async def get_user() -> UserResponse
# Collects all Pydantic models referenced
```

## Properties

```python
mirror.model_count   # Number of collected models
mirror.model_names   # List of model names
```

## CLI

```bash
vorte manifest:types --app main:app --output types/api.d.ts
```

This uses `TypeMirror.from_app()` internally to scan the app and generate TypeScript.
