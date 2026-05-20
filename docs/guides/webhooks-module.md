# Webhooks Module

Webhook management with delivery, retry, and HMAC verification.

## Setup

```python
from vorte import WebhooksModule

app.register(WebhooksModule())
```

## Features

- **Webhook Registration** -- Register webhook endpoints
- **Signed Delivery** -- HMAC-signed payloads for security
- **Retry Logic** -- Exponential backoff for failed deliveries
- **Delivery Logs** -- Track all webhook deliveries and responses

## Workflow

1. Register a webhook URL
2. When an event occurs, Vorte sends an HTTP POST to the URL
3. The payload is signed with HMAC for verification
4. If delivery fails, retry with exponential backoff
5. All delivery attempts are logged
