# Built-in API Endpoints

Vorte automatically registers several built-in endpoints.

## Health & Probes

### `GET /health`

Full module health check.

```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "modules": {
      "database": {"status": "healthy"},
      "cache": {"status": "healthy"}
    }
  }
}
```

Returns `200` if all modules are healthy, `503` if any module is degraded.

### `GET /ready`

Kubernetes readiness probe. Returns `200` when the application is ready to accept traffic.

### `GET /live`

Kubernetes liveness probe. Returns `200` when the application process is alive.

## Framework Info

### `GET /_vorte/info`

Framework and runtime information.

```json
{
  "success": true,
  "data": {
    "framework": "Vorte",
    "version": "1.0.8",
    "python_version": "3.12.0",
    "platform": "linux",
    "module_count": 21,
    "route_count": 45
  }
}
```

## Prometheus Metrics

### `GET /_vorte/metrics`

Prometheus-formatted metrics (requires native engine):

```
vorte_serialization_time_ns 5100
vorte_database_wait_time_ns 2300
vorte_scheduling_latency_ns 1800
vorte_event_loop_lag_ns 450
vorte_buffered_spans_total 42
vorte_metrics_buffer_capacity_total 10000
```

## Dashboard API

### `GET /_vorte/dashboard/overview`

Complete dashboard overview including:
- Framework info and uptime
- Module list and states
- Route count
- Request metrics
- System stats (memory, CPU)

### `GET /_vorte/dashboard/modules`

Detailed list of all registered modules with:
- Name, version, description
- Current state
- Priority level
- Dependencies

### `GET /_vorte/dashboard/routes`

All registered routes with:
- HTTP path
- Methods (GET, POST, etc.)
- Route name
- Tags

### `GET /_vorte/dashboard/health`

Health check details for all modules.

### `GET /_vorte/dashboard/config`

Non-sensitive configuration dump. Sensitive fields (keys, secrets, passwords) are masked.

### `GET /_vorte/dashboard/events`

Event listeners registered on the application with listener counts.

### `GET /_vorte/dashboard/metrics`

Raw request metrics including:
- Total request count
- Per-path counts, errors, and latency
- Per-method counts
- Last 50 requests
