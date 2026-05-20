# Dashboard Module

Real-time admin dashboard built with Next.js, Tailwind CSS, and Framer Motion.

## Setup

```python
from vorte import DashboardModule

app.register(DashboardModule())
```

## Configuration

```env
VORTE_DASHBOARD_ENABLED=true
VORTE_DASHBOARD_PATH=/_vorte/dashboard
VORTE_DASHBOARD_AUTH_REQUIRED=false
```

## Access

Visit `http://localhost:8000/_vorte/dashboard` when the server is running.

## Dashboard API

The dashboard is served by a set of internal API endpoints:

| Endpoint | Description |
|----------|-------------|
| `/_vorte/dashboard/overview` | Framework info, uptime, modules, routes, metrics, system stats |
| `/_vorte/dashboard/modules` | Detailed list of all registered modules with state |
| `/_vorte/dashboard/routes` | All registered routes with methods and paths |
| `/_vorte/dashboard/health` | Health check details for all modules |
| `/_vorte/dashboard/config` | Non-sensitive configuration dump |
| `/_vorte/dashboard/events` | Event listeners and counts |
| `/_vorte/dashboard/metrics` | Raw request metrics |

## Features

- **Module Overview** -- See all registered modules and their states
- **Route Inspection** -- Browse all registered API routes
- **Health Monitoring** -- Real-time module health status
- **Request Metrics** -- Traffic, latency, and error rates
- **Configuration Viewer** -- View non-sensitive configuration
- **System Stats** -- Memory, CPU, and uptime information

## Building the Dashboard

```bash
vorte dashboard:build
```

This builds the Next.js dashboard and copies the static assets to the module's `static/` directory.

## Technology Stack

- **Next.js** -- React framework
- **Tailwind CSS** -- Utility-first CSS
- **Framer Motion** -- Animation library
