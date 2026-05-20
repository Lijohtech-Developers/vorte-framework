# Multi-Tenancy Module

Multi-tenant application support with multiple isolation strategies.

## Setup

```python
from vorte import MultiTenancyModule

app.register(MultiTenancyModule())
```

## Configuration

```env
VORTE_TENANCY_STRATEGY=header
VORTE_TENANCY_ISOLATION=schema
```

## Resolution Strategies

| Strategy | Example | Description |
|----------|---------|-------------|
| `subdomain` | `tenant1.myapp.com` | Resolve from subdomain |
| `header` | `X-Tenant-ID: tenant1` | Resolve from HTTP header |
| `path` | `/t/tenant1/...` | Resolve from URL path |
| `jwt` | JWT claim `tenant_id` | Resolve from JWT token |

## Isolation Levels

| Level | Description |
|-------|-------------|
| `schema` | Separate database schemas per tenant |
| `database` | Separate databases per tenant |

## API Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/tenancy/current` | GET | Get current tenant |
| `/tenancy/tenants` | GET | List all tenants |
| `/tenancy/tenants` | POST | Create tenant |
| `/tenancy/tenants/{id}` | PUT | Update tenant |
| `/tenancy/tenants/{id}` | DELETE | Delete tenant |

## Usage

```python
from vorte.modules.tenancy import CurrentTenant

@app.get("/api/v1/data")
async def get_data(tenant: CurrentTenant):
    # tenant is automatically resolved based on strategy
    data = await get_tenant_data(tenant.id)
    return success_response(data=data)
```

## TenancyResolver

The resolver middleware:
1. Intercepts every request
2. Extracts tenant identifier based on strategy
3. Looks up tenant in database
4. Injects `CurrentTenant` into the request context
