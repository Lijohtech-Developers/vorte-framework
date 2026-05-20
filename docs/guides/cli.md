# CLI Reference

Vorte provides 30+ CLI commands organized by category. The CLI is available via the `vorte` command after installation.

## Usage

```bash
vorte <command> [options]
vorte --help
```

## Project Commands

### `vorte new <name>`

Create a new Vorte project.

```bash
vorte new my-app                    # Minimal template
vorte new my-ai-app --template ai-saas  # AI SaaS template
```

Options:
- `--template` / `-t` -- Project template: `minimal` (default) or `ai-saas`

### `vorte serve`

Start the development server.

```bash
vorte serve                         # Default: localhost:8000
vorte serve --host 0.0.0.0 --port 3000
vorte serve --watch                 # Auto-reload on changes
vorte serve --workers 4             # Multi-worker (production)
```

Options:
- `--host` / `-H` -- Bind address (default: `0.0.0.0`)
- `--port` / `-p` -- Bind port (default: `8000`)
- `--watch` / `-w` -- Enable auto-reload
- `--workers` / `-W` -- Number of workers

### `vorte routes`

List all registered routes from `main:app`.

### `vorte modules`

List all registered modules with their state.

### `vorte health`

Check application health via HTTP.

## Generator Commands

### `vorte make:module <name>`

Generate a module scaffold with router, service, models, schemas, and events.

```bash
vorte make:module blog
vorte make:module admin --with-auth
```

### `vorte make:job <name>`

Generate a background job class.

```bash
vorte make:job send_welcome_email
```

### `vorte make:agent <name>`

Generate an AI agent class with tool support.

```bash
vorte make:agent support_bot
```

### `vorte make:pipeline <name>`

Generate a multi-step AI pipeline.

```bash
vorte make:pipeline content_pipeline
```

### `vorte make:migration <name>`

Generate an Alembic migration file.

```bash
vorte make:migration create_users_table
```

## Database Commands

### `vorte migrate`

Run pending database migrations.

### `vorte migrate:rollback`

Rollback the last migration(s).

```bash
vorte migrate:rollback --step 1
```

### `vorte migrate:fresh`

Drop all tables and re-run all migrations.

```bash
vorte migrate:fresh          # Drop + migrate
vorte migrate:fresh --seed   # Drop + migrate + seed
```

### `vorte migrate:status`

Show migration status (current, head, applied, pending).

### `vorte db:seed`

Run database seeders.

## AI Commands

### `vorte ai:models`

List available AI models with pricing information.

### `vorte ai:costs`

Show AI cost report.

```bash
vorte ai:costs               # All time
vorte ai:costs --period today
vorte ai:costs --period week
```

## M-Pesa Commands

### `vorte mpesa:setup`

Interactive M-Pesa credential setup wizard.

### `vorte mpesa:balance`

Check M-Pesa account balance.

## DevOps Commands

### `vorte docker:init`

Generate `Dockerfile` and `docker-compose.yml`.

### `vorte docker:build`

Build the Docker image.

### `vorte k8s:init`

Generate Kubernetes Deployment and Service manifests.

```bash
vorte k8s:init --name my-app
```

### `vorte bench`

HTTP benchmark utility.

```bash
vorte bench                                    # Benchmark localhost:8000
vorte bench --url http://localhost:8000/api    # Custom URL
vorte bench --requests 1000 --concurrency 50   # Load test
```

Options:
- `--url` / `-u` -- Target URL
- `--requests` / `-n` -- Number of requests (default: 100)
- `--concurrency` / `-c` -- Concurrent connections (default: 10)

## Manifest Commands

### `vorte manifest:export`

Export OpenAPI schema and route tree as JSON.

```bash
vorte manifest:export
vorte manifest:export --app main:app --output manifest.json
```

### `vorte manifest:validate`

Validate current app against a saved manifest. Reports schema drift.

```bash
vorte manifest:validate --manifest vorte-manifest.json
```

### `vorte manifest:types`

Generate TypeScript interface declarations from Pydantic models.

```bash
vorte manifest:types
vorte manifest:types --output types/api.d.ts
```

## Other Commands

### `vorte cache:stats`

Show cache module statistics.

### `vorte search:index`

Manage MeiliSearch indexes.

```bash
vorte search:index list
vorte search:index create myindex
vorte search:index delete myindex
```

### `vorte dashboard:build`

Build the Next.js admin dashboard.
