# Changelog

All notable changes to the Vorte Framework are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.8] - 2026-05-20

### Added

- Vorte runtime kernel evolution with bucketed memory pools
- Zero-copy buffer protocol for serialization
- Structured concurrency with `VorteTaskGroup` and `PyCancellationToken`
- Native Prometheus metrics endpoint at `/_vorte/metrics`
- Compiled DAG execution graph engine (`PyExecutionGraph`)
- Multi-format serialization: JSON, MessagePack, CBOR, Protobuf
- Buffer pooling with RAII buffer return (4-bucket: 4KB, 16KB, 64KB, 256KB)

## [1.0.7] - 2026-05-18

### Added

- `FastSerializer` with automatic backend selection (native > orjson > stdlib)
- `@lazy_schema` decorator for deferred Pydantic validation
- `_LazyPayload` wrapper with zero-copy raw access and cached validation
- Database performance mode (`@performance_mode` decorator)
- `PreparedSQLManager` for prepared SQL statement management
- Benchmark utility for serialization performance testing

## [1.0.6] - 2026-05-15

### Fixed

- Router duplicate `kwargs` parameter in route registration
- Planner list type annotations for proper type checking

## [1.0.5] - 2026-05-13

### Added

- Stable engine compilation with maturin build system
- Look-ahead query planner for automatic N+1 detection
- `@select_related` decorator for manual eager loading
- `N1Detector` with configurable threshold
- `QueryPlanner` with SQLAlchemy `selectinload` integration
- `VorteAPIRoute` with automatic relationship inference from Pydantic models

## [1.0.0] - 2026-05-10

### Added

- Initial release of Vorte Framework
- Core application class (`Vorte`) with ASGI 3.0 support
- Module system with priority-based initialization and dependency validation
- 21 built-in modules:
  - AI (OpenAI, Anthropic, Gemini, Mistral) with cost tracking and routing
  - Agents (tools, memory, RAG, pipelines, guardrails, prompts)
  - Auth (JWT, OAuth, API keys, RBAC, MFA, sessions)
  - Cache (4-layer: L1 memory, L2 Redis, L3 CDN, L4 database)
  - Database (SQLAlchemy async, N+1 detection, query planning)
  - Queue (priority, backpressure, dead letter queue, retry)
  - Storage (local filesystem, AWS S3)
  - Search (MeiliSearch, pgvector)
  - Mailer (SMTP)
  - M-Pesa (STK Push, C2B, B2C, B2B)
  - Payments (Stripe, Paystack)
  - Notifications (in-app, email, push, SMS)
  - Security (Helmet, CSRF, XSS, rate limiting, bot detection)
  - Webhooks (HMAC signing, retry, delivery logs)
  - Sockets (WebSocket with rooms and broadcasting)
  - GraphQL (auto-schema, playground, subscriptions)
  - Multi-Tenancy (subdomain, header, path, JWT resolution)
  - Feature Flags (boolean, percentage rollout, targeting, A/B testing)
  - i18n (translation files, interpolation, locale detection)
  - Logging (structured JSON logging)
  - Dashboard (Next.js admin panel)
- Dependency injection container with singleton, request, and transient scopes
- `@wire` decorator for compile-time graph wiring
- API versioning with URL and header strategies
- Route deprecation with Sunset and Link headers
- Standard response envelope with success/data/meta/ai/error/pagination
- `VorteSSEResponse` for Server-Sent Events
- `VorteStreamResponse` for zero-copy raw streaming
- `VorteExecutor` work-stealing thread pool with `@safe_route` decorator
- `WasmSandbox` for isolated WebAssembly execution
- `TypeMirror` for automatic TypeScript interface generation
- CLI with 30+ commands (new, serve, routes, make:module, migrate, etc.)
- Testing framework (`VorteTestClient`, `AIMocker`, `MpesaMocker`, `VorteTestCase`)
- Rust native engine with 8 crates:
  - `vorte-http` -- Zero-copy HTTP types
  - `vorte-router` -- Radix tree router
  - `vorte-core` -- Hyper/Tokio server
  - `vorte-py` -- PyO3 ASGI bridge
  - `vorte-scheduler` -- Priority task scheduler
  - `vorte-queue` -- Async queue engine
  - `vorte-serde` -- Multi-format serialization
  - `vorte-graph` -- DAG execution graph
- Kubernetes health probes (`/health`, `/ready`, `/live`)
- Built-in admin dashboard with real-time monitoring
- Docker and Kubernetes manifest generation
- CI/CD with GitHub Actions (3-platform wheel build + PyPI publish)
- MIT License

[1.0.8]: https://github.com/Lijohtech-Developers/vorte-framework/releases/tag/v1.0.8
[1.0.7]: https://github.com/Lijohtech-Developers/vorte-framework/releases/tag/v1.0.7
[1.0.6]: https://github.com/Lijohtech-Developers/vorte-framework/releases/tag/v1.0.6
[1.0.5]: https://github.com/Lijohtech-Developers/vorte-framework/releases/tag/v1.0.5
[1.0.0]: https://github.com/Lijohtech-Developers/vorte-framework/releases/tag/v1.0.0
