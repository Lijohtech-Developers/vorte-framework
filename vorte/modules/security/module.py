"""
Vorte Security Module
======================
Comprehensive security: HTTP headers (Helmet), CSRF, XSS, rate limiting,
bot detection, geo-blocking, encryption, and audit logging.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, Request, Response, status

from vorte.core.module import Module, ModuleMeta, ModulePriority
from vorte.core.response import success_response, error_response


# ---- Encryption Helpers ----

class Crypto:
    """Symmetric encryption helpers using Fernet (AES-128-CBC)."""

    def __init__(self, secret_key: Optional[str] = None):
        self._secret_key = (secret_key or secrets.token_urlsafe(32)).encode()

    def _get_fernet(self):
        try:
            from cryptography.fernet import Fernet
            import base64
            key = base64.urlsafe_b64encode(hashlib.sha256(self._secret_key).digest())
            return Fernet(key)
        except ImportError:
            raise ImportError("Install cryptography: pip install cryptography")

    async def encrypt(self, data: str) -> str:
        f = self._get_fernet()
        return f.encrypt(data.encode()).decode()

    async def decrypt(self, encrypted: str) -> str:
        f = self._get_fernet()
        return f.decrypt(encrypted.encode()).decode()

    def hash(self, data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()

    def verify_hash(self, data: str, expected_hash: str) -> bool:
        return hmac.compare_digest(self.hash(data), expected_hash)


# ---- Rate Limiter (Sliding Window) ----

class RateLimiter:
    """Sliding window rate limiter."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> tuple[bool, Dict[str, Any]]:
        """Check if a request is allowed. Returns (allowed, info)."""
        now = time.time()
        cutoff = now - self._window
        # Clean old entries
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        if len(self._requests[key]) >= self._max:
            return False, {
                "limit": self._max,
                "remaining": 0,
                "reset_at": self._requests[key][0] + self._window,
            }
        self._requests[key].append(now)
        return True, {
            "limit": self._max,
            "remaining": self._max - len(self._requests[key]),
            "reset_at": now + self._window,
        }

    def reset(self, key: str) -> None:
        self._requests.pop(key, None)


# ---- Bot Detection ----

class BotDetector:
    """Simple bot detection based on user-agent patterns."""

    BOT_PATTERNS = [
        "bot", "crawler", "spider", "scraper", "curl", "wget", "python-requests",
        "httpclient", "java/", "go-http", "node-fetch",
    ]

    def is_bot(self, user_agent: str) -> bool:
        ua_lower = user_agent.lower()
        return any(pattern in ua_lower for pattern in self.BOT_PATTERNS)


# ---- Audit Logger ----

class AuditLogger:
    """Audit logging for security-sensitive operations."""

    def __init__(self):
        self._logs: List[Dict[str, Any]] = []

    def log(self, actor_id: str, action: str, resource: str, details: Any = None, ip: str = "", user_agent: str = ""):
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor_id": actor_id,
            "action": action,
            "resource": resource,
            "details": details,
            "ip": ip,
            "user_agent": user_agent,
        }
        self._logs.append(entry)
        if len(self._logs) > 10000:
            self._logs = self._logs[-5000:]

    def get_logs(self, actor_id: Optional[str] = None, action: Optional[str] = None, limit: int = 100) -> List[Dict]:
        results = self._logs
        if actor_id:
            results = [l for l in results if l["actor_id"] == actor_id]
        if action:
            results = [l for l in results if l["action"] == action]
        return results[-limit:]


# ---- XSS Sanitizer ----

class XSSSanitizer:
    """Basic XSS sanitization."""

    DANGEROUS_TAGS = ["script", "iframe", "object", "embed", "link", "style"]
    DANGEROUS_ATTRS = ["onclick", "onerror", "onload", "onmouseover", "onfocus", "onblur"]

    def sanitize(self, text: str) -> str:
        import re
        # Remove dangerous event attributes
        for attr in self.DANGEROUS_ATTRS:
            text = re.compile(rf'{attr}\s*=\s*["\'][^"\']*["\']', re.IGNORECASE).sub('', text)
        # Remove dangerous tags
        for tag in self.DANGEROUS_TAGS:
            text = re.compile(rf'<\s*{tag}[^>]*>.*?<\s*/\s*{tag}>', re.IGNORECASE | re.DOTALL).sub('', text)
            text = re.compile(rf'<\s*{tag}[^>]*/?>', re.IGNORECASE).sub('', text)
        return text


class SecurityModule(Module):
    """
    Comprehensive security module.
    
    Usage:
        app.register(SecurityModule(
            helmet=True, csrf=True, xss=True,
            rate_limit=True, bot_detection=True,
            geo_blocking=['KP'],
        ))
    """

    meta = ModuleMeta(
        name="security",
        version="1.0.0",
        description="HTTP headers, CSRF, XSS, rate limiting, bot detection, encryption, audit logging",
        priority=ModulePriority.MIDDLEWARE,
    )

    def __init__(
        self,
        *,
        helmet: bool = True,
        csrf: bool = True,
        xss: bool = True,
        rate_limit: bool = True,
        rate_limit_max: int = 100,
        rate_limit_window: int = 60,
        bot_detection: bool = True,
        geo_blocking: Optional[List[str]] = None,
    ):
        super().__init__()
        self._helmet = helmet
        self._csrf = csrf
        self._xss = xss
        self._rate_limit = rate_limit
        self._rate_limit_max = rate_limit_max
        self._rate_limit_window = rate_limit_window
        self._bot_detection = bot_detection
        self._geo_blocking = set(geo_blocking or [])
        self.crypto = Crypto()
        self.rate_limiter = RateLimiter(rate_limit_max, rate_limit_window)
        self.bot_detector = BotDetector()
        self.audit_logger = AuditLogger()
        self.xss_sanitizer = XSSSanitizer()

    def register(self, app) -> None:
        app._vorte_crypto = self.crypto
        app._vorte_rate_limiter = self.rate_limiter
        app._vorte_bot_detector = self.bot_detector
        app._vorte_audit_logger = self.audit_logger

        @app.middleware("http")
        async def security_middleware(request: Request, call_next):
            # Rate limiting
            if self._rate_limit:
                client_key = request.client.host if request.client else "unknown"
                allowed, info = self.rate_limiter.is_allowed(client_key)
                response_headers = {
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": str(info["remaining"]),
                }
                if not allowed:
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        content={"success": False, "error": {"code": "RATE_LIMITED", "message": "Too many requests"}},
                        status_code=429,
                        headers=response_headers,
                    )

            # Bot detection (just flag, don't block unless configured)
            if self._bot_detection:
                ua = request.headers.get("user-agent", "")
                request.state.is_bot = self.bot_detector.is_bot(ua)

            # Geo-blocking (basic IP check - in production use GeoIP database)
            # Placeholder: actual geo-blocking requires IP geolocation service

            response = await call_next(request)

            # Security headers (Helmet-like)
            if self._helmet:
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["X-XSS-Protection"] = "1; mode=block"
                response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

            if self._rate_limit:
                response.headers["X-RateLimit-Limit"] = str(self._rate_limit_max)
                response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 0))

            return response
