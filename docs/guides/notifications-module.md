# Notifications Module

Multi-channel notification delivery.

## Setup

```python
from vorte import NotificationsModule

app.register(NotificationsModule())
```

## Channels

- **In-app** -- Notifications stored in the database
- **Email** -- Via the Mailer module
- **Push** -- Mobile/desktop push notifications
- **SMS** -- Via configured SMS provider

## Features

- Template-based messages
- Channel preferences per user
- Batch sending
- Delivery status tracking
