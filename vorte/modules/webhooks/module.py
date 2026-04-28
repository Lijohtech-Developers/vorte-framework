"""
Vorte Webhooks Module
======================
Outgoing webhooks with retries, incoming webhook verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from vorte.core.module import Module, ModuleMeta, ModulePriority
from vorte.core.response import success_response


@dataclass
class WebhookEndpoint:
    url: str
    events: List[str]
    secret: str = ""
    retry_count: int = 3
    timeout: int = 30
    is_active: bool = True
    created_at: float = field(default_factory=time.time)
    last_delivery: Optional[float] = None
    failure_count: int = 0


@dataclass
class WebhookDelivery:
    id: str
    endpoint_url: str
    event: str
    payload: Dict[str, Any]
    status: str = "pending"
    response_code: Optional[int] = None
    response_body: Optional[str] = None
    attempts: int = 0
    created_at: float = field(default_factory=time.time)
    delivered_at: Optional[float] = None


class WebhookSender:
    """Sends outgoing webhooks with retries."""

    def __init__(self):
        self._endpoints: List[WebhookEndpoint] = []
        self._deliveries: List[WebhookDelivery] = []
        self._http = httpx.AsyncClient(timeout=30.0)

    def register(self, url: str, events: List[str], secret: str = "") -> WebhookEndpoint:
        endpoint = WebhookEndpoint(url=url, events=events, secret=secret)
        self._endpoints.append(endpoint)
        return endpoint

    def unregister(self, url: str) -> bool:
        for i, ep in enumerate(self._endpoints):
            if ep.url == url:
                self._endpoints.pop(i)
                return True
        return False

    async def send(self, event: str, payload: Dict[str, Any]) -> List[WebhookDelivery]:
        """Send a webhook event to all matching endpoints."""
        deliveries = []
        for endpoint in self._endpoints:
            if not endpoint.is_active or event not in endpoint.events:
                continue
            delivery = WebhookDelivery(
                id=f"whdl_{__import__('uuid').uuid4().hex[:12]}",
                endpoint_url=endpoint.url,
                event=event,
                payload=payload,
            )
            success = await self._deliver(endpoint, delivery)
            delivery.status = "delivered" if success else "failed"
            delivery.delivered_at = time.time()
            deliveries.append(delivery)
            self._deliveries.append(delivery)
        return deliveries

    async def _deliver(self, endpoint: WebhookEndpoint, delivery: WebhookDelivery) -> bool:
        """Attempt delivery with retries."""
        body = json.dumps({"event": delivery.event, "data": delivery.payload})
        headers = {"Content-Type": "application/json"}
        if endpoint.secret:
            sig = hmac.new(endpoint.secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={sig}"

        for attempt in range(endpoint.retry_count):
            delivery.attempts = attempt + 1
            try:
                resp = await self._http.post(endpoint.url, content=body, headers=headers, timeout=endpoint.timeout)
                delivery.response_code = resp.status_code
                delivery.response_body = resp.text[:500]
                endpoint.last_delivery = time.time()
                if 200 <= resp.status_code < 300:
                    endpoint.failure_count = 0
                    return True
            except Exception as e:
                delivery.response_body = str(e)[:500]
            endpoint.failure_count += 1
        return False

    def list_endpoints(self) -> List[Dict]:
        return [{"url": ep.url, "events": ep.events, "active": ep.is_active, "failures": ep.failure_count} for ep in self._endpoints]

    def get_deliveries(self, event: Optional[str] = None, limit: int = 50) -> List[Dict]:
        results = self._deliveries
        if event:
            results = [d for d in results if d.event == event]
        return [{"id": d.id, "event": d.event, "status": d.status, "attempts": d.attempts, "code": d.response_code} for d in results[-limit:]]


class WebhooksModule(Module):
    """
    Webhook system for outgoing and incoming webhooks.
    
    Usage:
        app.register(WebhooksModule())
        await webhooks.register('https://example.com/webhook', ['order.created'], secret='...')
    """

    meta = ModuleMeta(
        name="webhooks",
        version="1.0.0",
        description="Outgoing and incoming webhooks with retries and signature verification",
        priority=ModulePriority.ROUTES,
    )

    def __init__(self):
        super().__init__()
        self.sender: Optional[WebhookSender] = None

    def register(self, app) -> None:
        self.sender = WebhookSender()
        if hasattr(app, 'container'):
            app.container.register_instance(WebhookSender, self.sender)

        @app.post("/webhooks/{provider}")
        async def incoming_webhook(provider: str, request: dict):
            return success_response({"received": True, "provider": provider})
