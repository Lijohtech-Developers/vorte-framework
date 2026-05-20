# Auth Module

Complete authentication with JWT, OAuth, API keys, RBAC, MFA, and session management.

## Setup

```python
from vorte import AuthModule

app.register(AuthModule())
```

## Configuration

```env
VORTE_AUTH_STRATEGY=jwt
VORTE_AUTH_SECRET_KEY=your-secret-key
VORTE_AUTH_TOKEN_EXPIRY_MINUTES=60
VORTE_AUTH_REFRESH_EXPIRY_DAYS=7
VORTE_AUTH_REFRESH_TOKENS=true
VORTE_AUTH_MFA=false
```

## Features

### JWT Authentication

```python
from vorte.modules.auth import JWTHandler

# Tokens are issued with configurable expiry
# Access tokens: token_expiry_minutes (default: 60)
# Refresh tokens: refresh_expiry_days (default: 7)
```

### OAuth2 Providers

Configure OAuth providers in settings:

```env
VORTE_AUTH_OAUTH_PROVIDERS={"google": {"client_id": "...", "client_secret": "..."}}
```

Supported flows: authorization code, implicit

### API Key Authentication

API keys for programmatic access with scoped permissions.

### Role-Based Access Control (RBAC)

Define roles and permissions:

```python
from vorte.modules.auth import require_role

@app.get("/admin/users")
@require_role("admin")
async def admin_users():
    return success_response(data=[...])
```

### Multi-Factor Authentication (MFA/TOTP)

Enable MFA in settings:

```env
VORTE_AUTH_MFA=true
```

### Session Management

Track and manage user sessions with:
- Session creation/validation
- Session revocation
- Concurrent session limits

### Route Guards

```python
from vorte.modules.auth import require_auth, require_role

@app.get("/profile")
@require_auth
async def get_profile():
    return success_response(data={...})

@app.delete("/admin/users/{user_id}")
@require_role("admin")
async def delete_user(user_id: int):
    return success_response()
```

## Models & Schemas

The module provides pre-built Pydantic schemas for:
- Login/Register requests
- Token responses
- User profiles
- MFA setup/verification
- OAuth callbacks
