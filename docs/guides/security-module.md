# Security Module

Security middleware with rate limiting, CSRF, XSS protection, and bot detection.

## Setup

```python
from vorte import SecurityModule

app.register(SecurityModule())
```

## Configuration

```env
VORTE_SECURITY_HELMET=true
VORTE_SECURITY_CSRF=true
VORTE_SECURITY_XSS=true
VORTE_SECURITY_RATE_LIMIT=true
VORTE_SECURITY_RATE_LIMIT_MAX=100
VORTE_SECURITY_RATE_LIMIT_WINDOW=60
VORTE_SECURITY_BOT_DETECTION=false
VORTE_SECURITY_GEO_BLOCKING=false
```

## Features

### Security Headers (Helmet)

Automatically adds security headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security`
- And more...

### CSRF Protection

Cross-Site Request Forgery token validation for state-changing requests.

### XSS Protection

Input sanitization to prevent Cross-Site Scripting attacks.

### Rate Limiting

Configurable per-IP rate limiting:

```env
VORTE_SECURITY_RATE_LIMIT_MAX=100    # Max requests
VORTE_SECURITY_RATE_LIMIT_WINDOW=60  # Per seconds
```

### Bot Detection

Detect and block automated requests.

### Geo-Blocking

Block or allow traffic based on geographic location.
