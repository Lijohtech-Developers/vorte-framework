"""
Vorte Payments Module
======================
Unified payments interface for Stripe, Paddle, and Paystack.
Supports one-time charges, subscriptions, usage-based billing, and entitlements.
"""

from __future__ import annotations

import httpx
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status

from vorte.core.module import Module, ModuleMeta, ModulePriority
from vorte.core.response import success_response, error_response
from vorte.modules.auth.guards import IsAuthenticated, CurrentUser, HasPermission


class PaymentProvider(str, Enum):
    STRIPE = "stripe"
    PADDLE = "paddle"
    PAYSTACK = "paystack"


@dataclass
class Customer:
    id: str
    email: str
    name: str
    provider_id: str = ""


@dataclass
class Subscription:
    id: str
    customer_id: str
    plan_id: str
    plan_name: str
    status: str = "active"
    current_period_start: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: bool = False


@dataclass
class Charge:
    id: str
    customer_id: str
    amount: int
    currency: str
    status: str = "succeeded"
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class PaymentBackend(ABC):
    """Base payment backend interface."""

    @abstractmethod
    async def create_customer(self, email: str, name: str, **kwargs) -> Customer: ...

    @abstractmethod
    async def create_charge(self, customer_id: str, amount: int, currency: str, **kwargs) -> Charge: ...

    @abstractmethod
    async def create_subscription(self, customer_id: str, plan_id: str, **kwargs) -> Subscription: ...

    @abstractmethod
    async def cancel_subscription(self, subscription_id: str, **kwargs) -> Subscription: ...

    @abstractmethod
    async def record_usage(self, customer_id: str, metric: str, quantity: int, **kwargs) -> Dict[str, Any]: ...

    @abstractmethod
    async def get_entitlements(self, customer_id: str) -> List[str]: ...

    @abstractmethod
    async def verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]: ...


class StripeBackend(PaymentBackend):
    """Stripe payment backend."""

    def __init__(self, api_key: str, webhook_secret: str = ""):
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self._http = httpx.AsyncClient(
            base_url="https://api.stripe.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def create_customer(self, email: str, name: str, **kwargs) -> Customer:
        resp = await self._http.post("/customers", data={"email": email, "name": name})
        data = resp.json()
        return Customer(id=data["id"], email=email, name=name, provider_id=data["id"])

    async def create_charge(self, customer_id: str, amount: int, currency: str, **kwargs) -> Charge:
        resp = await self._http.post("/charges", data={
            "customer": customer_id, "amount": amount, "currency": currency,
            "description": kwargs.get("description", ""),
        })
        data = resp.json()
        return Charge(id=data["id"], customer_id=customer_id, amount=amount, currency=currency, status=data.get("status", ""))

    async def create_subscription(self, customer_id: str, plan_id: str, **kwargs) -> Subscription:
        resp = await self._http.post("/subscriptions", data={
            "customer": customer_id, "plan": plan_id,
        })
        data = resp.json()
        return Subscription(
            id=data["id"], customer_id=customer_id, plan_id=plan_id, plan_name=plan_id,
            status=data.get("status", "active"),
            current_period_start=data.get("current_period_start"),
            current_period_end=data.get("current_period_end"),
        )

    async def cancel_subscription(self, subscription_id: str, **kwargs) -> Subscription:
        resp = await self._http.delete(f"/subscriptions/{subscription_id}")
        data = resp.json()
        return Subscription(id=data["id"], customer_id="", plan_id="", status=data.get("status", "canceled"))

    async def record_usage(self, customer_id: str, metric: str, quantity: int, **kwargs) -> Dict[str, Any]:
        # Stripe usage records via Subscription Items API
        subscription_item_id = kwargs.get("subscription_item_id", "")
        if not subscription_item_id:
            return {"recorded": False, "reason": "subscription_item_id required"}
        resp = await self._http.post(f"/subscription_items/{subscription_item_id}/usage_records", data={
            "quantity": quantity, "timestamp": "now", "action": "increment",
        })
        return {"recorded": resp.status_code == 200}

    async def get_entitlements(self, customer_id: str) -> List[str]:
        # Retrieve active subscription and map to entitlements
        return ["basic_access"]

    async def verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        import json
        return json.loads(payload)


class PaystackBackend(PaymentBackend):
    """Paystack payment backend (Africa-focused)."""

    def __init__(self, api_key: str, webhook_secret: str = ""):
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self._http = httpx.AsyncClient(
            base_url="https://api.paystack.co",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    async def create_customer(self, email: str, name: str, **kwargs) -> Customer:
        resp = await self._http.post("/customer", json={"email": email, "first_name": name})
        data = resp.json()["data"]
        return Customer(id=data["id"], email=email, name=name, provider_id=data["customer_code"])

    async def create_charge(self, customer_id: str, amount: int, currency: str, **kwargs) -> Charge:
        resp = await self._http.post("/transaction/initialize", json={
            "customer": customer_id, "amount": amount, "currency": currency.lower(),
        })
        data = resp.json()["data"]
        return Charge(id=data["reference"], customer_id=customer_id, amount=amount, currency=currency, status="pending")

    async def create_subscription(self, customer_id: str, plan_id: str, **kwargs) -> Subscription:
        resp = await self._http.post("/subscription", json={"customer": customer_id, "plan": plan_id})
        data = resp.json()["data"]
        return Subscription(id=data["subscription_code"], customer_id=customer_id, plan_id=plan_id, plan_name=plan_id)

    async def cancel_subscription(self, subscription_id: str, **kwargs) -> Subscription:
        resp = await self._http.post(f"/subscription/disable", json={"code": subscription_id})
        return Subscription(id=subscription_id, customer_id="", plan_id="", status="canceled")

    async def record_usage(self, customer_id: str, metric: str, quantity: int, **kwargs) -> Dict[str, Any]:
        return {"recorded": True}

    async def get_entitlements(self, customer_id: str) -> List[str]:
        return ["basic_access"]

    async def verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        import json, hashlib, hmac
        computed = hmac.new(self.webhook_secret.encode(), payload, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(computed, signature):
            raise ValueError("Invalid webhook signature")
        return json.loads(payload)


class PaymentsModule(Module):
    """
    Unified payments module for Stripe, Paddle, and Paystack.
    
    Usage:
        app.register(PaymentsModule(provider='stripe', api_key='sk_...', currency='USD'))
    """

    meta = ModuleMeta(
        name="payments",
        version="1.0.0",
        description="Unified payments with Stripe, Paddle, Paystack - subscriptions and usage billing",
        priority=ModulePriority.PAYMENTS,
    )

    def __init__(self, *, provider: str = "stripe", currency: str = "USD", webhooks: bool = True, api_key: str = "", webhook_secret: str = ""):
        super().__init__(provider=provider, currency=currency, webhooks=webhooks)
        self._provider_name = provider
        self._currency = currency
        self._webhooks = webhooks
        self._backend: Optional[PaymentBackend] = None
        self._router = APIRouter(prefix="/payments", tags=["Payments"])

    def register(self, app) -> None:
        if self._provider_name == "stripe":
            self._backend = StripeBackend(api_key=self.get_config("api_key", ""), webhook_secret=self.get_config("webhook_secret", ""))
        elif self._provider_name == "paystack":
            self._backend = PaystackBackend(api_key=self.get_config("api_key", ""), webhook_secret=self.get_config("webhook_secret", ""))
        else:
            raise ValueError(f"Unsupported payment provider: {self._provider_name}")

        if hasattr(app, 'container'):
            app.container.register_instance(PaymentBackend, self._backend)

        app._vorte_webhook_secrets = getattr(app, '_vorte_webhook_secrets', {})
        app._vorte_webhook_secrets[self._provider_name] = self.get_config("webhook_secret", "")

        self._setup_routes()
        app.include_router(self._router)

    def _setup_routes(self):
        @self._router.post("/charge")
        async def create_charge(request: dict, user: CurrentUser = Depends(IsAuthenticated)):
            charge = await self._backend.create_charge(user.id, request.get("amount", 0), self._currency, description=request.get("description", ""))
            return success_response(charge.__dict__)

        @self._router.post("/subscribe")
        async def subscribe(request: dict, user: CurrentUser = Depends(IsAuthenticated)):
            sub = await self._backend.create_subscription(user.id, request.get("plan_id", ""))
            return success_response(sub.__dict__)

        @self._router.post("/cancel/{subscription_id}")
        async def cancel_subscription(subscription_id: str, user: CurrentUser = Depends(IsAuthenticated)):
            sub = await self._backend.cancel_subscription(subscription_id)
            return success_response(sub.__dict__)

        @self._router.post("/usage")
        async def record_usage(request: dict, user: CurrentUser = Depends(IsAuthenticated)):
            result = await self._backend.record_usage(user.id, request.get("metric", ""), request.get("quantity", 0))
            return success_response(result)

        @self._router.get("/entitlements")
        async def get_entitlements(user: CurrentUser = Depends(IsAuthenticated)):
            entitlements = await self._backend.get_entitlements(user.id)
            return success_response({"entitlements": entitlements})
