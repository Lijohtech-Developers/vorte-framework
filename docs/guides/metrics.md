# Prometheus Metrics

Vorte exposes Prometheus-formatted metrics at `/_vorte/metrics`.

## Endpoint

```
GET /_vorte/metrics
```

Requires the native Rust engine (`MetricsCollector`).

## Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `vorte_serialization_time_ns` | gauge | Time spent serializing responses (nanoseconds) |
| `vorte_database_wait_time_ns` | gauge | Time waiting for database queries (nanoseconds) |
| `vorte_scheduling_latency_ns` | gauge | Task scheduling latency (nanoseconds) |
| `vorte_event_loop_lag_ns` | gauge | Event loop lag (nanoseconds) |
| `vorte_buffered_spans_total` | counter | Total buffered telemetry spans |
| `vorte_metrics_buffer_capacity_total` | gauge | Metrics ring buffer capacity (default: 10,000) |

## MetricsCollector

The native Rust `MetricsCollector` stores metrics in a ring buffer:

- **Capacity**: 10,000 entries
- **Eviction**: Oldest entries evicted when at capacity
- **Operations**: `push()`, `drain()`, `tail(n)`

```python
from vorte._vorte_engine import MetricsCollector

collector = MetricsCollector()
collector.push("latency_ns", 5100)

# Drain all entries
entries = collector.drain()

# Get last N entries
recent = collector.tail(100)
```

## Prometheus Integration

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'vorte'
    metrics_path: '/_vorte/metrics'
    static_configs:
      - targets: ['localhost:8000']
```

## Grafana Dashboard

Use the metrics to build Grafana dashboards tracking:
- Request latency distribution
- Database query performance
- Task scheduling efficiency
- Event loop health
- Serialization overhead
