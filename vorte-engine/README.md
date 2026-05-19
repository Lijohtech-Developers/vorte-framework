# VORTE Engine

Rust-first native execution engine for VORTE Framework. Provides a high-performance HTTP runtime that integrates seamlessly with FastAPI while accelerating the low-level request lifecycle.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Python Layer                        │
│  FastAPI App ── Routes, DI, Middleware, Pydantic         │
├─────────────────────────────────────────────────────────┤
│  vorte-py (_vorte_engine)                                │
│  VorteEngine ── ASGI Bridge ── GIL Management            │
├─────────────────────────────────────────────────────────┤
│  vorte-core                                              │
│  Server ── Connection Handler ── Pipeline                │
├─────────────────────────────────────────────────────────┤
│  vorte-router                                            │
│  Radix Tree ── Zero-Allocation Matching ── Method Dispatch│
├─────────────────────────────────────────────────────────┤
│  vorte-http                                              │
│  repr(C) Structs ── Zero-Copy Headers ── URL Parsing     │
├─────────────────────────────────────────────────────────┤
│  Tokio Multi-Threaded Runtime + Hyper 1.x                │
│  HTTP/1.1 · HTTP/2 · TLS (rustls) · Keep-Alive          │
└─────────────────────────────────────────────────────────┘
```

## Crate Overview

### `vorte-http` — Zero-Copy HTTP Types

Defines FFI-safe, `repr(C)` structs for representing HTTP requests and responses with zero heap allocation during hot-path access.

| File | Purpose |
|------|---------|
| `method.rs` | `Method` enum — 9 HTTP methods, `repr(C)`, convertible to/from `http::Method` |
| `raw.rs` | `RawRequest`, `RawHeader`, `RawResponse`, `Scheme` — offset/length based views into a shared buffer |
| `request.rs` | `HttpRequest` — safe wrapper over `RawRequest`, constructable from hyper requests |
| `response.rs` | `HttpResponse` — builder pattern, converts to `hyper::Response<Full<Bytes>>` |
| `headers.rs` | `HeaderMap` — case-insensitive header storage with pre-hashed lookups |
| `parse.rs` | `ParsedUri`, `parse_query_string`, `decode_percent` — zero-copy URL decomposition |

**Key design**: `RawHeader` stores `(name_offset, name_len, value_offset, value_len)` tuples. `RawRequest` stores path, query, body, and headers all as offset/length pairs into a single contiguous buffer. Accessors return borrowed slices — no cloning.

### `vorte-router` — Radix Tree Router

A concurrent radix tree router that performs zero-allocation route matching with method-based dispatch.

| File | Purpose |
|------|---------|
| `params.rs` | `Params` — stack-allocated array of 16 `Param` structs (key: `&'static str`, value: offset+length) |
| `node.rs` | `Node` — radix tree node with prefix, handlers per method, static/param/wildcard children |
| `tree.rs` | `Router` — insert routes, freeze for concurrent reads, match with method dispatch |

**Matching algorithm**:
1. Walk down the tree matching node prefixes
2. Try static children first (exact byte match on first byte)
3. Then param children (capture segment between `/` delimiters)
4. Then wildcard children (capture remaining path)
5. Return handler ID + extracted parameters as offset/length pairs

**Precedence**: Static > Param > Wildcard (matches FastAPI/Starlette behavior).

**Concurrency model**: Routes are inserted via `RwLock<Node>`. After `freeze()`, the tree is stored as `Arc<Node>` for lock-free concurrent reads across all tokio worker threads.

### `vorte-core` — Hyper/Tokio Server Engine

The HTTP server built on hyper 1.x and tokio, handling TCP accept loops, connection lifecycle, HTTP parsing, and request dispatch.

| File | Purpose |
|------|---------|
| `server.rs` | `Server` + `ServerBuilder` — configures and runs the tokio runtime with TCP listener |
| `connection.rs` | `ConnectionHandler` + `VorteService` — handles individual connections via hyper `serve_connection` |
| `pipeline.rs` | `Pipeline` + `HandlerFn` — pre/post routing hooks + handler dispatch |
| `tls.rs` | TLS configuration via `tokio-rustls` (feature-gated behind `tls`) |

**Connection flow**:
1. `TcpListener::accept()` in a tokio `select!` with ctrl-C signal
2. Each connection wrapped in `hyper_util::rt::TokioIo` for hyper compatibility
3. `http1::Builder::serve_connection()` or `http2::Builder::serve_connection()`
4. `VorteService` implements `hyper::service::Service` — performs route matching and dispatches to pipeline
5. Connection count tracked via `AtomicU64` with configurable max connections

### `vorte-py` — PyO3 Python Bindings

Exposes the Rust engine as a native Python extension module `_vorte_engine`.

| File | Purpose |
|------|---------|
| `lib.rs` | `#[pymodule]` registration — defines `_vorte_engine` Python module |
| `engine.rs` | `VorteEngine` pyclass — `add_route()`, `run()`, `route_count`, `is_running` |
| `bridge.rs` | ASGI scope builder, `AsgiReceive`/`AsgiSend` callables, `run_asgi_call()` |
| `handler.rs` | `create_python_handler()` — bridges tokio async to Python asyncio via `spawn_blocking` + GIL |

**ASGI Bridge Design**:

```
Tokio Worker Thread                    Blocking Thread Pool
┌──────────────────┐                   ┌──────────────────────┐
│ HTTP Request      │                   │ Python::with_gil()   │
│ Route Match       │                   │                      │
│ Body Collect      │──spawn_blocking──▶│ Build ASGI Scope     │
│                   │                   │ Create Receive/Send  │
│                   │                   │ asyncio.new_event_loop│
│                   │                   │ run_until_complete() │
│                   │◀──response────────│ Capture Response     │
│ Send Response     │                   │ Release GIL          │
└──────────────────┘                   └──────────────────────┘
```

- Each `spawn_blocking` thread gets its own `asyncio` event loop (thread-local)
- GIL is only held during Python execution; released during all I/O
- Request body is fully collected in Rust async context before entering Python
- Response is captured from `AsgiSend` state and converted to `hyper::Response`

## Python Integration

### `vorte/engine.py`

Python-side wrapper that:
1. Attempts to import `_vorte_engine` (the compiled Rust extension)
2. If available: extracts routes from the FastAPI app, registers them in the Rust router, starts the Rust server
3. If unavailable: falls back to `uvicorn.run()` transparently

### Usage with FastAPI

```python
from fastapi import FastAPI
from vorte import VorteEngine

app = FastAPI()

@app.get("/users/{id}")
async def get_user(id: str):
    return {"id": id}

@app.post("/users")
async def create_user():
    return {"created": True}

engine = VorteEngine(app)
engine.run(host="0.0.0.0", port=8000)
```

### Usage with Vorte Framework

```python
from vorte import Vorte, VorteEngine

app = Vorte(auto_load=True)

@app.get("/health")
async def health():
    return {"status": "ok"}

engine = VorteEngine(app)
engine.run(port=8000, workers=4)
```

### API Reference

#### `VorteEngine(app=None, *, host="0.0.0.0", port=8000, workers=1)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `app` | FastAPI/Vorte | None | The ASGI application to serve |
| `host` | str | "0.0.0.0" | Bind address |
| `port` | int | 8000 | Bind port |
| `workers` | int | 1 | Tokio worker threads (0 = auto-detect) |

#### `VorteEngine.run(app=None, *, host=None, port=None, workers=None)`

Starts the server. Accepts overrides for all constructor parameters. Blocks until shutdown (ctrl-C).

#### `VorteEngine.add_route(method, path)`

Manually register a route in the Rust router.

#### `VorteEngine.is_native` (property)

Returns `True` if the Rust extension is loaded, `False` if using uvicorn fallback.

#### `VorteEngine.route_count` (property)

Returns the number of routes registered in the engine.

## Build Instructions

### Prerequisites

- **Rust** 1.75+ (`rustup install stable`)
- **Visual Studio Build Tools 2022** with "Desktop development with C++" workload (Windows)
- **Python** 3.11+ with development headers
- **maturin** (`pip install maturin`)

### Building

```bash
# Build all Rust crates
cd vorte-engine
cargo build --release

# Build and install Python extension
maturin develop --release

# Or build a wheel
maturin build --release
```

### Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `http1` | Yes | HTTP/1.1 support |
| `http2` | No | HTTP/2 support (compile with `--features http2`) |
| `tls` | No | TLS via tokio-rustls (compile with `--features tls`) |

```bash
# Build with HTTP/2 and TLS support
cargo build --release --features http2,tls
```

### Cross-compilation

```bash
# Linux
rustup target add x86_64-unknown-linux-gnu
cargo build --release --target x86_64-unknown-linux-gnu

# macOS
rustup target add x86_64-apple-darwin
cargo build --release --target x86_64-apple-darwin

# ARM64 (Apple Silicon)
rustup target add aarch64-apple-darwin
cargo build --release --target aarch64-apple-darwin
```

## ASGI Compatibility

VORTE implements the ASGI 3.0 specification for HTTP requests:

| ASGI Feature | Status |
|-------------|--------|
| `http` scope type | Supported |
| `http.request` message | Supported |
| `http.response.start` message | Supported |
| `http.response.body` message | Supported |
| `http.disconnect` message | Supported |
| Path parameters in scope | Supported |
| Query string in scope | Supported |
| Headers (bytes tuples) | Supported |
| Server/client addresses | Supported |
| HTTP version reporting | Supported |
| WebSocket (`websocket` scope) | Planned |
| Lifespan (`lifespan` scope) | Planned |
| HTTP/2 push (`http.response.push`) | Planned |

### ASGI Scope Structure

The engine builds the following scope dict for each request:

```python
{
    "type": "http",
    "asgi": {"version": "3.0", "spec_version": "2.3"},
    "http_version": "1.1",
    "method": "GET",
    "scheme": "http",
    "path": "/users/123",
    "query_string": b"page=1",
    "root_path": "",
    "headers": [(b"host", b"localhost:8000"), ...],
    "server": ("127.0.0.1", 8000),
    "client": ("192.168.1.1", 54321),
    "path_params": {"id": "123"},
}
```

### FastAPI Compatibility

| Feature | How It Works |
|---------|-------------|
| Route decorators | Routes declared via `@app.get(...)` etc. are extracted from FastAPI and mirrored in Rust |
| Dependency injection | Fully preserved — FastAPI's DI runs when the ASGI app handles the request |
| Pydantic models | Fully preserved — request/response validation happens in FastAPI |
| Middleware | Fully preserved — Starlette middleware chain executes normally |
| Background tasks | Fully preserved — works through ASGI lifecycle |
| Exception handlers | Fully preserved — handled by FastAPI's error handling |
| OpenAPI generation | Fully preserved — FastAPI generates docs as usual |
| `APIRouter` | Supported — routes from included routers are extracted |
| CORS | Preserved — middleware runs in Python |
| Streaming responses | Supported via ASGI body chunks |
| Static files | Preserved — handled by FastAPI/Starlette mounts |

## Performance Characteristics

### Zero-Copy Hot Path

The request routing path performs zero heap allocations:

1. **Method parsing**: `Method::from_standard()` returns a `Copy` enum
2. **Route matching**: traverses `Arc<Node>` tree with borrowed references
3. **Parameter extraction**: `Params` is stack-allocated (192 bytes for 16 params)
4. **Header access**: `HeaderMap` uses pre-hashed lookups, returns borrowed `&[u8]`

### 404 Short-Circuit

Requests that don't match any route return 404 directly from Rust — no Python code executes. This eliminates GIL acquisition, event loop creation, and all Python overhead for invalid routes.

### Lock-Free Concurrent Reads

After `freeze()`, the radix tree is stored as `Arc<Node>`. All tokio worker threads read the tree concurrently without any locks or atomic operations on the hot path.

### GIL Management

- GIL is only held during `spawn_blocking` Python execution
- Tokio worker threads never hold the GIL
- Multiple requests can be processed concurrently (Rust-side) while Python handles one at a time (GIL-bound)
- Future optimization: release GIL during Python `await` points

## Extensibility

### Adding Native Rust Handlers

```rust
use vorte_core::pipeline::HandlerFn;

let handler: HandlerFn = Arc::new(|req, method, path, match_result, peer, server| {
    Box::pin(async move {
        // Handle entirely in Rust — no Python
        http::Response::builder()
            .status(200)
            .body(Full::new(Bytes::from("Hello from Rust")))
            .unwrap()
    })
});
```

### Adding Middleware Hooks

```rust
pipeline.add_pre_routing_hook(Arc::new(|method, path| {
    // Rate limiting, auth checks, etc.
    HookAction::Continue
}));

pipeline.add_post_routing_hook(Arc::new(|method, path, status| {
    Box::pin(async move {
        // Logging, metrics, etc.
    })
}));
```

### HTTP/3 / QUIC

The architecture is designed for QUIC extensibility. The `connection.rs` module can be extended with a `serve_http3` method using `quinn` or similar QUIC implementations. The `ServerBuilder` would accept a `quic` feature flag analogous to the existing `http2` support.

## Testing

```bash
# Run Rust unit tests
cd vorte-engine
cargo test --workspace --exclude vorte-py

# Run Python tests
pip install -e .
python -c "from vorte import VorteEngine; print('OK')"

# Benchmark router
cargo test -p vorte-router -- --nocapture
```

## Configuration

Environment variables follow the `VORTE_` prefix convention from the parent framework:

| Variable | Default | Description |
|----------|---------|-------------|
| `VORTE_HOST` | 0.0.0.0 | Server bind address |
| `VORTE_PORT` | 8000 | Server bind port |
| `VORTE_WORKERS` | auto | Tokio worker thread count |
| `VORTE_MAX_CONNECTIONS` | 65536 | Maximum concurrent connections |
| `VORTE_KEEP_ALIVE` | 75s | HTTP keep-alive timeout |
| `VORTE_TCP_NODELAY` | true | Disable Nagle's algorithm |
| `VORTE_HTTP2` | false | Enable HTTP/2 |
| `VORTE_SHUTDOWN_TIMEOUT` | 30s | Graceful shutdown drain time |

## License

MIT
