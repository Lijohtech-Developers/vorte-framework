# Configuration

Vorte uses a layered configuration system with environment variables, `.env` files, and Python-based configuration.

## Loading Configuration

### Automatic (.env file)

Place a `.env` file in your project root. All variables are prefixed with `VORTE_`:

```env
VORTE_APP_NAME=My Application
VORTE_APP_ENV=production
VORTE_APP_DEBUG=false
VORTE_DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db
```

Settings are auto-loaded when creating a Vorte app:

```python
from vorte import Vorte
app = Vorte()  # Reads .env automatically
```

### Programmatic

```python
from vorte import Settings

# Load from environment
settings = Settings.from_env()

# Access values
print(settings.database.url)
print(settings.is_production())
```

### Dynamic Configuration

```python
app = Vorte()
app.configure(
    app_debug=True,
    cors_origins=["http://localhost:3000"],
)

# Load from a Python module
app.use_config("config.production")
```

## Settings Sections

### Application Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `VORTE_APP_NAME` | `"Vorte App"` | Application name |
| `VORTE_APP_ENV` | `"development"` | Environment: development/production/testing |
| `VORTE_APP_DEBUG` | `false` | Enable debug mode |
| `VORTE_APP_URL` | `"http://localhost:8000"` | Application URL |
| `VORTE_APP_KEY` | `""` | Application secret key |
| `VORTE_API_PREFIX` | `"/api"` | API route prefix |
| `VORTE_DEFAULT_VERSION` | `"v1"` | Default API version |
| `VORTE_TIMEZONE` | `"UTC"` | Application timezone |
| `VORTE_CORS_ORIGINS` | `["*"]` | Allowed CORS origins |

### Database (`settings.database`)

| Field | Default | Description |
|-------|---------|-------------|
| `url` | `"sqlite+aiosqlite:///vorte.db"` | Database URL |
| `pool_size` | `5` | Connection pool size |
| `max_overflow` | `10` | Max overflow connections |
| `echo` | `false` | Echo SQL statements |
| `read_replica_urls` | `[]` | Read replica URLs |

### Redis (`settings.redis`)

| Field | Default | Description |
|-------|---------|-------------|
| `url` | `"redis://localhost:6379/0"` | Redis URL |
| `cache_url` | `None` | Dedicated cache Redis |
| `queue_url` | `None` | Dedicated queue Redis |

### Auth (`settings.auth`)

| Field | Default | Description |
|-------|---------|-------------|
| `strategy` | `"jwt"` | Auth strategy (jwt/session) |
| `secret_key` | `""` | JWT signing key |
| `refresh_tokens` | `true` | Enable refresh tokens |
| `mfa` | `false` | Enable MFA |
| `oauth_providers` | `{}` | OAuth provider configs |
| `token_expiry_minutes` | `60` | Access token lifetime |
| `refresh_expiry_days` | `7` | Refresh token lifetime |

### AI (`settings.ai`)

| Field | Default | Description |
|-------|---------|-------------|
| `default_model` | `"gpt-4"` | Default AI model |
| `fallback_providers` | `[]` | Fallback provider list |
| `cache_responses` | `true` | Cache AI responses |
| `track_costs` | `true` | Track AI costs |
| `max_tokens` | `4096` | Max generation tokens |
| `temperature` | `0.7` | Default temperature |
| `providers` | `{}` | Provider configurations |

### Cache (`settings.cache`)

| Field | Default | Description |
|-------|---------|-------------|
| `driver` | `"redis"` | Cache driver (redis/memory) |
| `default_ttl` | `3600` | Default TTL in seconds |
| `l1_enabled` | `true` | Enable L1 in-memory cache |
| `l1_max_size` | `1000` | L1 max entries |
| `l2_enabled` | `true` | Enable L2 Redis cache |
| `l3_cdn_url` | `None` | CDN URL for L3 |
| `l4_db_cache` | `false` | Enable L4 DB cache |

### Queue (`settings.queue`)

| Field | Default | Description |
|-------|---------|-------------|
| `driver` | `"redis"` | Queue driver (redis/memory) |
| `default_retries` | `3` | Max retry attempts |
| `default_retry_delay` | `60` | Seconds between retries |
| `concurrency` | `10` | Max concurrent workers |

### Storage (`settings.storage`)

| Field | Default | Description |
|-------|---------|-------------|
| `driver` | `"local"` | Storage driver (local/s3) |
| `bucket` | `""` | S3 bucket name |
| `cdn_url` | `None` | CDN URL |
| `local_path` | `"./storage"` | Local storage path |
| `access_key` | `""` | AWS access key |
| `secret_key` | `""` | AWS secret key |
| `region` | `"us-east-1"` | AWS region |

### Mailer (`settings.mailer`)

| Field | Default | Description |
|-------|---------|-------------|
| `driver` | `"smtp"` | Mail driver |
| `host` | `"localhost"` | SMTP host |
| `port` | `587` | SMTP port |
| `username` | `""` | SMTP username |
| `password` | `""` | SMTP password |
| `from_address` | `"noreply@example.com"` | From email address |
| `from_name` | `"Vorte App"` | From name |

### M-Pesa (`settings.mpesa`)

| Field | Default | Description |
|-------|---------|-------------|
| `environment` | `"sandbox"` | sandbox/production |
| `consumer_key` | `""` | Daraja API key |
| `consumer_secret` | `""` | Daraja API secret |
| `shortcode` | `""` | Business shortcode |
| `passkey` | `""` | Lipa Na M-Pesa passkey |
| `callback_url` | `""` | Webhook URL |

### Payments (`settings.payments`)

| Field | Default | Description |
|-------|---------|-------------|
| `provider` | `"stripe"` | Payment provider (stripe/paystack) |
| `currency` | `"USD"` | Default currency |
| `webhook_secret` | `""` | Webhook signing secret |
| `api_key` | `""` | Provider API key |

### Security (`settings.security`)

| Field | Default | Description |
|-------|---------|-------------|
| `helmet` | `true` | Security headers |
| `csrf` | `true` | CSRF protection |
| `xss` | `true` | XSS protection |
| `rate_limit` | `true` | Rate limiting |
| `rate_limit_max` | `100` | Max requests per window |
| `rate_limit_window` | `60` | Window in seconds |
| `bot_detection` | `false` | Bot detection |
| `geo_blocking` | `false` | Geographic blocking |

### Search (`settings.search`)

| Field | Default | Description |
|-------|---------|-------------|
| `engine` | `"meilisearch"` | Search engine |
| `meilisearch_url` | `"http://localhost:7700"` | MeiliSearch URL |
| `meilisearch_key` | `""` | MeiliSearch API key |
| `pgvector_connection` | `None` | pgvector connection |

### Tenancy (`settings.tenancy`)

| Field | Default | Description |
|-------|---------|-------------|
| `strategy` | `"header"` | Resolution strategy (subdomain/header/path/jwt) |
| `isolation` | `"schema"` | Isolation level (schema/database) |

### i18n (`settings.i18n`)

| Field | Default | Description |
|-------|---------|-------------|
| `default_locale` | `"en"` | Default language |
| `fallback_locale` | `"en"` | Fallback language |
| `locales_dir` | `"./locales"` | Translation files directory |

### Performance (`settings.performance`)

| Field | Default | Description |
|-------|---------|-------------|
| `http2` | `false` | Enable HTTP/2 |
| `brotli` | `false` | Enable Brotli compression |
| `brotli_threshold` | `1024` | Compression threshold (bytes) |
| `protobuf` | `false` | Enable Protobuf serialization |

### Dashboard (`settings.dashboard`)

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `true` | Enable dashboard |
| `path` | `"/_vorte/dashboard"` | Dashboard URL path |
| `auth_required` | `false` | Require authentication |

## Environment Helpers

```python
from vorte.core.config import env, env_bool, env_int, env_list

# String value (looks for VORTE_ prefix)
url = env("DATABASE_URL")

# Boolean (true/1/yes/on)
debug = env_bool("DEBUG", default=False)

# Integer
port = env_int("PORT", default=8000)

# Comma-separated list
origins = env_list("CORS_ORIGINS", separator=",")
```

## Environment Checks

```python
settings = Settings.from_env()

settings.is_production()     # VORTE_APP_ENV == "production"
settings.is_development()    # VORTE_APP_ENV == "development"
settings.is_testing()        # VORTE_APP_ENV == "testing"
```
