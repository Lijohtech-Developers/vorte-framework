# Cache Module

4-layer caching system with L1 (in-memory), L2 (Redis), L3 (CDN), and L4 (database).

## Setup

```python
from vorte import CacheModule

app.register(CacheModule())
```

## Configuration

```env
VORTE_CACHE_DRIVER=redis
VORTE_CACHE_DEFAULT_TTL=3600
VORTE_CACHE_L1_ENABLED=true
VORTE_CACHE_L1_MAX_SIZE=1000
VORTE_CACHE_L2_ENABLED=true
```

## Cache Layers

| Layer | Backend | Speed | Use For |
|-------|---------|-------|---------|
| L1 | In-memory (LRU) | Fastest | Hot data, < 1000 entries |
| L2 | Redis | Fast | Shared cache across workers |
| L3 | CDN headers | Medium | Static content, API responses |
| L4 | Database | Slow | Persistent cache |

## Features

- **TTL Management** -- Set per-key time-to-live
- **Cache Invalidation** -- Pattern-based and explicit invalidation
- **Cache Decorators** -- `@cached` decorator for route handlers
- **Statistics** -- Hit/miss rates, memory usage

## CLI

```bash
vorte cache:stats    # Show cache statistics
```
