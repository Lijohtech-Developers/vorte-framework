# Serialization

FastSerializer provides high-performance multi-format serialization with automatic backend selection.

## Backend Selection

FastSerializer automatically picks the fastest available backend:

| Priority | Backend | Performance | Notes |
|----------|---------|-------------|-------|
| 1 | Native Rust | Fastest | Built into the Rust engine |
| 2 | orjson | 3-10x faster than stdlib | C-extension, included in dependencies |
| 3 | stdlib json | Baseline | Always available |

```python
from vorte import FastSerializer

print(FastSerializer.backend)   # "native", "orjson", or "stdlib"
print(FastSerializer.is_native())  # True if using native or orjson
```

## Basic Usage

```python
from vorte import FastSerializer

data = {"name": "Vorte", "version": "1.0.8", "features": ["ai", "modules"]}

# Serialize to bytes
encoded = FastSerializer.dumps(data)

# Serialize to string
encoded_str = FastSerializer.dumps_str(data)

# Deserialize
decoded = FastSerializer.loads(encoded)
```

## Multi-Format Serialization

```python
# JSON (default)
json_bytes = FastSerializer.dumps(data, format="json")

# MessagePack
msgpack_bytes = FastSerializer.dumps(data, format="msgpack")

# CBOR
cbor_bytes = FastSerializer.dumps(data, format="cbor")

# Protobuf
proto_bytes = FastSerializer.dumps(data, format="protobuf")

# Deserialize from any format
decoded = FastSerializer.loads(msgpack_bytes, format="msgpack")
```

### Content-Type Mapping

| Format | Content-Type |
|--------|-------------|
| JSON | `application/json` |
| MsgPack | `application/x-msgpack` |
| CBOR | `application/cbor` |
| Protobuf | `application/x-protobuf` |

## Benchmark Utility

```python
data = {"users": [{"id": i, "name": f"User {i}"} for i in range(100)]}

metrics = FastSerializer.benchmark_serialize(data)
# Returns:
# {
#   "preprocessing_ns": 1200,
#   "serialization_ns": 3400,
#   "copying_ns": 500,
#   "total_ns": 5100,
#   "payload_size_bytes": 2456
# }
```

## Lazy Schema Validation

Defer Pydantic validation for better performance on routes that don't immediately need validated data:

```python
from vorte import lazy_schema
from pydantic import BaseModel

class UserCreate(BaseModel):
    name: str
    email: str
    age: int = None

@lazy_schema(UserCreate)
@app.post("/users")
async def create_user(request):
    # Access raw bytes without validation
    raw_bytes = request._vorte_lazy_payload.raw

    # Validate on demand (cached)
    user = request._vorte_lazy_payload.validate()

    # Pass through to background job without validation overhead
    await background_process(raw_bytes)
```

The `@lazy_schema` decorator marks the function with `_vorte_lazy_schema = True`. The `_LazyPayload` wrapper:
- Stores raw bytes from the request body
- Validates against the Pydantic model on first `.validate()` call
- Caches the validated result
- Provides `.raw` property for zero-copy access to unvalidated bytes

## Enterprise Type Support

FastSerializer handles Python enterprise types automatically:

```python
from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID

data = {
    "id": UUID("12345678-1234-5678-1234-567812345678"),
    "created_at": datetime(2026, 5, 20, 10, 30, 0),
    "birth_date": date(1990, 1, 1),
    "meeting_time": time(14, 30),
    "price": Decimal("19.99"),
}

encoded = FastSerializer.dumps(data)
decoded = FastSerializer.loads(encoded)
```

## Zero-Copy Buffer Protocol

When using the native Rust engine:

```python
from vorte._vorte_engine import NativeSerde, VorteBuffer

serde = NativeSerde()
buffer = serde.serialize_to_buffer(data)  # VorteBuffer
view = buffer.to_memoryview()  # Zero-copy memory view
```

Buffers are pooled in a 4-bucket pool (4KB, 16KB, 64KB, 256KB) with RAII return on drop.
