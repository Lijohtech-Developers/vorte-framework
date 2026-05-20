# Logging Module

Structured logging with multiple outputs.

## Setup

```python
from vorte import LoggingModule

app.register(LoggingModule())
```

## Features

- **Structured JSON Logging** -- Machine-parseable log format
- **Multiple Outputs** -- Console, file, remote logging services
- **Log Level Configuration** -- DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Request Logging** -- Automatic request/response logging
- **Context Enrichment** -- Add trace IDs, user IDs, and other context
