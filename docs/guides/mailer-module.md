# Mailer Module

Email sending with SMTP backend.

## Setup

```python
from vorte import MailerModule

app.register(MailerModule())
```

## Configuration

```env
VORTE_MAILER_DRIVER=smtp
VORTE_MAILER_HOST=smtp.gmail.com
VORTE_MAILER_PORT=587
VORTE_MAILER_USERNAME=you@gmail.com
VORTE_MAILER_PASSWORD=app-password
VORTE_MAILER_FROM_ADDRESS=noreply@example.com
VORTE_MAILER_FROM_NAME=My App
```

## Features

- **SMTP Driver** -- Standard SMTP email sending
- **HTML/Text** -- Support for both HTML and plain text emails
- **Templates** -- Template-based email generation
- **Queue Integration** -- Send emails via the Queue module for background processing
