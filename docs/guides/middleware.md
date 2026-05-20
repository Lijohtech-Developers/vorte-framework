# Middleware

Vorte includes built-in middleware and supports custom middleware.

## Built-in Middleware

### CORS Middleware

Automatically added to all Vorte applications. Configured via `settings.cors_origins`:

```env
VORTE_CORS_ORIGINS=http://localhost:3000,https://myapp.com
```

### Request Tracing Middleware

Automatically adds:
- `X-Request-ID` header (unique per request)
- `X-Powered-By: Vorte` header
- `X-Response-Time` header (in milliseconds)
- Trace ID propagation via `ContextVar`

### VersioningMiddleware

Handles API versioning and deprecation headers:

```python
from vorte.core.router import VersioningMiddleware

middleware = VersioningMiddleware(default_version="v1", strategy="url")
```

### ErrorHandlerMiddleware

Catches unhandled exceptions and returns standardized error responses:

```python
from vorte.middleware.error_handler import ErrorHandlerMiddleware

app.add_middleware(ErrorHandlerMiddleware)
```

Returns:

```json
{
  "success": false,
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "An unexpected error occurred"
  },
  "meta": {
    "request_id": "req_..."
  }
}
```

### RequestTimingMiddleware

Adds `X-Response-Time` header to responses:

```python
from vorte.middleware.request_timing import RequestTimingMiddleware

app.add_middleware(RequestTimingMiddleware)
```

## Custom Middleware

### ASGI Middleware

```python
@app.middleware("http")
async def custom_middleware(request, call_next):
    # Before request
    start = time.time()

    response = await call_next(request)

    # After request
    elapsed = time.time() - start
    response.headers["X-Custom-Time"] = f"{elapsed:.3f}s"

    return response
```

### Class-based Middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware

class CustomMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Custom"] = "value"
        return response

app.add_middleware(CustomMiddleware)
```

### Exception Handlers

```python
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return error_response(
        code="INVALID_VALUE",
        message=str(exc),
        status_code=400,
    )

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return error_response(
        code="NOT_FOUND",
        message="Resource not found",
        status_code=404,
    )
```
