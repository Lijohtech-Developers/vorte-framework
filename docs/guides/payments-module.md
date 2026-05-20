# Payments Module

Multi-provider payment processing with Stripe and Paystack backends.

## Setup

```python
from vorte import PaymentsModule

app.register(PaymentsModule())
```

## Configuration

```env
VORTE_PAYMENTS_PROVIDER=stripe
VORTE_PAYMENTS_CURRENCY=USD
VORTE_PAYMENTS_API_KEY=sk_live_...
VORTE_PAYMENTS_WEBHOOK_SECRET=whsec_...
```

## Supported Providers

### Stripe

```python
# Full Stripe integration:
# - Customers
# - Charges
# - Subscriptions
# - Usage records
# - Entitlements
# - Webhook verification
```

### Paystack (Africa-focused)

```python
# Paystack integration:
# - Charge authorization
# - HMAC webhook verification
# - African payment methods (mobile money, bank transfer)
```

## API Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/payments/charge` | POST | Create a charge |
| `/payments/subscribe` | POST | Create a subscription |
| `/payments/cancel/{id}` | POST | Cancel a subscription |
| `/payments/usage` | GET | Get usage records |
| `/payments/entitlements` | GET | Get entitlements |

## Webhooks

Webhook signatures are verified automatically using HMAC.

## PaymentBackend ABC

Implement custom payment backends:

```python
from vorte.modules.payments import PaymentBackend

class CustomBackend(PaymentBackend):
    async def charge(self, amount, currency, **kwargs):
        ...

    async def subscribe(self, customer_id, plan_id, **kwargs):
        ...

    async def cancel(self, subscription_id, **kwargs):
        ...
```
