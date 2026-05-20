# Project Scaffolding

## Templates

The `vorte new` command supports two project templates:

### Minimal Template (default)

```bash
vorte new my-app
```

Creates a minimal application with a single hello route:

```python
from vorte import Vorte

app = Vorte(auto_load=True)

@app.get("/")
async def index():
    return {"message": "Welcome to Vorte!"}
```

### AI SaaS Template

```bash
vorte new my-ai-app --template ai-saas
```

Creates a full-featured AI SaaS starter with:
- DatabaseModule (SQLAlchemy + PostgreSQL)
- AuthModule (JWT authentication)
- CacheModule (Redis caching)
- QueueModule (Background jobs)
- AIModule (Multi-provider AI)
- Pre-configured `.env` with all settings
- User registration/login routes
- AI chat endpoint
- Background job example

## Generated Files

### main.py

Application entry point with the Vorte app instance.

### .env

Complete environment configuration template with all available settings commented out.

### requirements.txt

Python dependencies matching the installed Vorte version.

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

Full stack with:
- **api** -- Vorte application
- **postgres** -- PostgreSQL database
- **redis** -- Redis cache/queue
- **worker** -- Background job worker
- **scheduler** -- Scheduled task runner

## Code Generators

### Module Generator

```bash
vorte make:module payments --with-auth
```

Creates a complete module scaffold with router, service, models, schemas, and event handlers.

### Job Generator

```bash
vorte make:job send_welcome_email
```

Creates a background job class:

```python
class SendWelcomeEmailJob:
    async def handle(self, *args, **kwargs):
        pass
```

### Agent Generator

```bash
vorte make:agent support_bot
```

Creates an AI agent class with tool support.

### Pipeline Generator

```bash
vorte make:pipeline content_pipeline
```

Creates a multi-step AI pipeline with configurable nodes.

### Migration Generator

```bash
vorte make:migration create_users_table
```

Creates an Alembic migration file.
