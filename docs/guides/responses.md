# Response Envelope

Every Vorte API response follows a standard envelope format for consistency.

## Envelope Structure

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "request_id": "req_a1b2c3d4e5f6",
    "version": "v1",
    "timestamp": "2026-05-20T10:30:00Z",
    "latency_ms": 12.5
  },
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 100,
    "total_pages": 5
  },
  "ai": {
    "model": "gpt-4",
    "provider": "openai",
    "tokens": 150,
    "cost": 0.003,
    "cached": false,
    "response_time_ms": 850
  },
  "error": {
    "code": "NOT_FOUND",
    "message": "User not found",
    "details": "...",
    "field": "user_id"
  }
}
```

All fields except `success` are optional and omitted when `None`.

## Response Helpers

### success_response

```python
from vorte import success_response

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = await get_user_from_db(user_id)
    return success_response(
        data=user,
        status_code=200,
        latency_ms=12.5,
    )
```

### error_response

```python
from vorte import error_response

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = await get_user_from_db(user_id)
    if not user:
        return error_response(
            code="NOT_FOUND",
            message="User not found",
            status_code=404,
            field_name="user_id",
        )
    return success_response(data=user)
```

### paginated_response

```python
from vorte import paginated_response

@app.get("/users")
async def list_users(page: int = 1, per_page: int = 20):
    users, total = await get_paginated_users(page, per_page)
    return paginated_response(
        data=users,
        page=page,
        per_page=per_page,
        total=total,
    )
```

### ai_response

```python
from vorte import ai_response

@app.post("/api/v1/chat")
async def chat(prompt: str):
    result = await ai_client.generate(prompt)
    return ai_response(
        data={"answer": result.text},
        model="gpt-4",
        provider="openai",
        tokens=result.token_count,
        cost=result.cost,
        cached=result.cached,
        response_time_ms=result.latency,
    )
```

## Streaming Responses

### Server-Sent Events (SSE)

```python
from vorte import VorteSSEResponse

@app.get("/events")
async def event_stream():
    async def generate():
        for i in range(10):
            yield {"count": i, "message": f"Event {i}"}
            await asyncio.sleep(1)
    return VorteSSEResponse(generate())
```

SSE responses set these headers:
- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `Connection: keep-alive`
- `X-Accel-Buffering: no`

Yielded values are serialized:
- `dict` -> JSON string
- `str` -> Plain text
- `bytes` -> Raw bytes

### Raw Streaming (Zero-Copy)

```python
from vorte import VorteStreamResponse

@app.get("/download")
async def download():
    async def generate():
        chunk = await read_file_chunk()
        while chunk:
            yield chunk
            chunk = await read_file_chunk()
    return VorteStreamResponse(generate())
```

`VorteStreamResponse` writes directly to the ASGI `send()` callable, bypassing Starlette overhead.

## Pagination Metadata

### Offset-based

```python
from vorte.core.response import PaginationMeta

meta = PaginationMeta.from_offset(page=1, per_page=20, total=100)
# meta.page = 1
# meta.per_page = 20
# meta.total = 100
# meta.total_pages = 5
```

### Cursor-based

```python
meta = PaginationMeta.from_cursor(cursor="abc123", limit=20, total=100)
# meta.next_cursor = "def456"
# meta.prev_cursor = "abc123"
```

## AI Metadata

```python
from vorte.core.response import AIMeta

ai_meta = AIMeta(
    model="gpt-4",
    provider="openai",
    tokens=150,
    cost=0.003,
    cached=False,
    response_time_ms=850,
)
```

## Response Headers

Every response includes:

| Header | Value | Description |
|--------|-------|-------------|
| `X-Request-ID` | `req_...` | Unique request identifier |
| `X-Powered-By` | `Vorte` | Framework identifier |
| `X-Response-Time` | `12.34ms` | Response latency |

Deprecated routes also include:
| Header | Value | Description |
|--------|-------|-------------|
| `Deprecation` | `true` | Route is deprecated |
| `Sunset` | RFC date | Removal date |
| `Link` | URL | Successor route |
