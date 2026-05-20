# Quick Start Guide

This guide walks you through creating a Vorte application from scratch.

## Step 1: Create a Project

```bash
pip install vorte
vorte new my-awesome-app
cd my-awesome-app
```

The `vorte new` command creates this structure:

```
my-awesome-app/
├── main.py            # Application entry point
├── .env               # Environment configuration
├── requirements.txt   # Python dependencies
├── Dockerfile         # Container configuration
├── docker-compose.yml # Full stack (API + Postgres + Redis)
└── .gitignore
```

## Step 2: Configure Environment

Edit `.env` with your settings:

```env
VORTE_APP_NAME=My Awesome App
VORTE_APP_ENV=development
VORTE_APP_DEBUG=true
VORTE_APP_URL=http://localhost:8000

VORTE_DATABASE_URL=sqlite+aiosqlite:///./app.db
VORTE_REDIS_URL=redis://localhost:6379/0

VORTE_AUTH_SECRET_KEY=change-me-to-a-random-string
```

## Step 3: Write Your Application

Edit `main.py`:

```python
from vorte import Vorte

app = Vorte(
    auto_load=True,      # Load all 21 modules
    title="My Awesome API",
    version="1.0.0",
)

@app.get("/api/v1/hello")
async def hello():
    return {"message": "Hello from Vorte!"}

@app.get("/api/v1/users")
async def list_users():
    users = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    return success_response(data=users)
```

## Step 4: Start the Server

```bash
vorte serve --watch
```

This starts uvicorn with auto-reload. Visit:

- **API**: http://localhost:8000/api/v1/hello
- **Dashboard**: http://localhost:8000/_vorte/dashboard
- **Health**: http://localhost:8000/health
- **Info**: http://localhost:8000/_vorte/info

## Step 5: Add a Module

Generate a custom module:

```bash
vorte make:module blog
```

This creates:

```
modules/
└── blog/
    ├── __init__.py
    ├── router.py      # Route definitions
    ├── service.py     # Business logic
    ├── models.py      # Database models
    ├── schemas.py     # Pydantic schemas
    └── events.py      # Event handlers
```

Register it in your app:

```python
from modules.blog import BlogModule

app.register(BlogModule())
```

## Step 6: Use the CLI

```bash
# List routes
vorte routes

# List modules
vorte modules

# Check health
vorte health

# Generate a background job
vorte make:job process_notifications

# Generate an AI agent
vorte make:agent support_bot

# Generate a migration
vorte make:migration create_users_table

# Run migrations
vorte migrate
```

## Next Steps

- [Configuration Guide](configuration.md) -- Configure all framework settings
- [Module System](modules.md) -- Build custom modules
- [AI Module](ai-module.md) -- Integrate AI providers
- [Auth Module](auth-module.md) -- Add authentication
- [Database Module](database-module.md) -- Set up database models
- [Deployment Guide](deployment.md) -- Deploy to production
