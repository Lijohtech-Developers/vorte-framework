# Deployment Guide

## Docker

### Generate Docker Files

```bash
vorte docker:init
```

This creates `Dockerfile` and `docker-compose.yml`.

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["vorte", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

The generated compose file includes:

| Service | Description |
|---------|-------------|
| `api` | Vorte application server |
| `postgres` | PostgreSQL database |
| `redis` | Redis cache and queue |
| `worker` | Background job worker |
| `scheduler` | Scheduled task runner |

### Build and Run

```bash
vorte docker:build
docker-compose up -d
```

## Kubernetes

### Generate Manifests

```bash
vorte k8s:init --name my-app
```

Creates `k8s/deployment.yml` and `k8s/service.yml`.

### Health Probes

Vorte provides Kubernetes-compatible endpoints:

```yaml
spec:
  containers:
  - name: api
    livenessProbe:
      httpGet:
        path: /live
        port: 8000
    readinessProbe:
      httpGet:
        path: /ready
        port: 8000
    startupProbe:
      httpGet:
        path: /health
        port: 8000
```

## Health Endpoints

| Endpoint | Status Codes | Description |
|----------|-------------|-------------|
| `/health` | 200 (healthy), 503 (degraded) | Full module health check |
| `/ready` | 200 | Kubernetes readiness probe |
| `/live` | 200 | Kubernetes liveness probe |

## Prometheus Metrics

Available at `/_vorte/metrics`:

```
vorte_serialization_time_ns 5100
vorte_database_wait_time_ns 2300
vorte_scheduling_latency_ns 1800
vorte_event_loop_lag_ns 450
vorte_buffered_spans_total 42
vorte_metrics_buffer_capacity_total 10000
```

## Production Configuration

```env
VORTE_APP_ENV=production
VORTE_APP_DEBUG=false

VORTE_DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/db
VORTE_DATABASE_POOL_SIZE=20
VORTE_DATABASE_MAX_OVERFLOW=30

VORTE_REDIS_URL=redis://redis:6379/0

VORTE_AUTH_SECRET_KEY=<strong-random-key>
VORTE_AUTH_TOKEN_EXPIRY_MINUTES=30

VORTE_CACHE_DRIVER=redis
VORTE_QUEUE_DRIVER=redis

VORTE_SECURITY_RATE_LIMIT=true
VORTE_SECURITY_RATE_LIMIT_MAX=100
VORTE_SECURITY_RATE_LIMIT_WINDOW=60

VORTE_PERFORMANCE_HTTP2=true
VORTE_PERFORMANCE_BROTLI=true
```

## Multi-Worker

```bash
# Via CLI
vorte serve --workers 4

# Via VorteEngine
from vorte import VorteEngine
engine = VorteEngine(app, workers=4)
engine.run()

# Via uvicorn directly
uvicorn main:app --workers 4
```

## Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support
        proxy_buffering off;
        proxy_cache off;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```
