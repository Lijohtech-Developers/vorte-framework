# Rust Native Engine

The Vorte engine is a Rust-based native execution engine that accelerates the HTTP request lifecycle for Python/FastAPI applications.

## Architecture

```
┌─────────────────────────────────────┐
│         Python / FastAPI            │
├─────────────────────────────────────┤
│    PyO3 ASGI Bridge (vorte-py)      │
├─────────────────────────────────────┤
│    Hyper/Tokio Server (vorte-core)  │
├─────────────────────────────────────┤
│    Radix Router (vorte-router)      │
│    HTTP Types (vorte-http)          │
│    Serde Engine (vorte-serde)       │
│    Scheduler (vorte-scheduler)      │
│    Queue Engine (vorte-queue)       │
│    DAG Graph (vorte-graph)          │
└─────────────────────────────────────┘
```

## Workspace Crates

### vorte-http -- Zero-Copy HTTP Types

FFI-safe `repr(C)` HTTP request/response types that use offset/length views into shared buffers.

- `RawRequest`, `RawResponse`, `RawHeader` -- FFI-safe structs
- `HttpRequest`, `HttpResponse` -- Safe wrappers
- `HeaderMap` -- Case-insensitive header storage
- `ParsedUri`, `parse_query_string`, `decode_percent` -- URI parsing

### vorte-router -- Radix Tree Router

Zero-allocation radix tree router with lock-free concurrent reads.

- **Matching precedence**: Static > Param > Wildcard
- **Lock-free**: After `freeze()`, stored as `Arc<Node>`
- **Stack-allocated params**: Fixed array of 16 parameters (192 bytes)

### vorte-core -- Hyper/Tokio Server

HTTP server engine built on Hyper 1.5 and Tokio 1.42.

- **HTTP/1.1** (default) and **HTTP/2** (feature flag)
- **TLS** support via `tokio-rustls` (feature flag)
- **WebSocket** via `tokio-tungstenite`
- **Pipeline**: Pre/post routing hooks
- **Connection tracking**: Atomic counter

### vorte-py -- PyO3 Python Bindings

Python bindings exposing 8 classes:

| Class | Description |
|-------|-------------|
| `VorteEngine` | Route registration and server start |
| `MetricsCollector` | Native metrics ring buffer (10,000 entries) |
| `RustExecutor` | Async task execution |
| `TaskScheduler` | Priority-based scheduling |
| `PyCancellationToken` | Cooperative cancellation bridge |
| `NativeQueue` | Rust-native queue operations |
| `NativeSerde` | Multi-format serialization |
| `VorteBuffer` | Zero-copy buffer access |
| `PyExecutionGraph` | DAG execution graph |

### vorte-scheduler -- Priority Task Scheduler

Priority-based task scheduler with work-stealing.

- Configurable worker threads (default: `available_parallelism * 2`)
- Priority levels: critical, high, normal, low
- Batch submission support
- Statistics tracking

### vorte-queue -- Async Queue Engine

Async queue with backpressure, dead letter queues, and optional Redis backend.

- Backpressure with watermarks (NORMAL, HIGH, FULL)
- Dead Letter Queue for permanently failed jobs
- Optional Redis backend (feature flag `redis-backend`)

### vorte-serde -- Multi-Format Serialization

Multi-format serialization with buffer pooling.

- **Formats**: JSON (0), MessagePack (1), CBOR (2), Protobuf (3)
- **BufferPool**: 4-bucket pool (4KB, 16KB, 64KB, 256KB), max 64 buffers per bucket
- **PooledBuffer**: RAII wrapper with automatic buffer return
- **Protobuf bridge**: `json_to_prost` / `prost_to_json` conversion

### vorte-graph -- DAG Execution Graph

Directed Acyclic Graph execution engine.

- 5 node types: `Middleware`, `Dependency`, `Query`, `Format`, `PythonFallback`
- Short-circuit support (middleware with `X-Short-Circuit` header)
- Cycle detection
- Recursive execution with error propagation

## ASGI 3.0 Compliance

The PyO3 bridge provides full ASGI 3.0 HTTP scope support:
- Path parameters
- Query string
- Headers
- Server/client addresses

WebSocket and Lifespan scopes are planned.

## Performance Design

- **Zero-copy hot path**: RawRequest/RawResponse use offset/length views
- **404 short-circuit**: Unmatched routes never enter Python
- **Lock-free routing**: Arc<Node> after freeze()
- **GIL release**: I/O operations release the Python GIL
- **Buffer pooling**: RAII buffer return prevents allocation churn

## Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `http1` | Yes | HTTP/1.1 support |
| `http2` | Yes | HTTP/2 support |
| `tls` | No | TLS via rustls |

## Building

```bash
# Prerequisites: Rust >= 1.75, Python >= 3.11, maturin
pip install maturin
maturin develop --release
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VORTE_HOST` | `0.0.0.0` | Server bind address |
| `VORTE_PORT` | `8000` | Server bind port |
| `VORTE_WORKERS` | `1` | Number of worker threads |
| `VORTE_MAX_CONNECTIONS` | `10000` | Max concurrent connections |
| `VORTE_KEEP_ALIVE` | `75` | Keep-alive timeout (seconds) |
| `VORTE_TCP_NODELAY` | `true` | Disable Nagle's algorithm |
| `VORTE_HTTP2` | `false` | Enable HTTP/2 |
| `VORTE_SHUTDOWN_TIMEOUT` | `30` | Graceful shutdown timeout |
