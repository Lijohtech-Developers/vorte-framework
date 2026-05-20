# M-Pesa Module

First-class Safaricom M-Pesa (Daraja API) integration for payments in Kenya and East Africa.

## Setup

```python
from vorte import MpesaModule

app.register(MpesaModule())
```

## Configuration

```env
VORTE_MPESA_ENVIRONMENT=sandbox
VORTE_MPESA_CONSUMER_KEY=your-key
VORTE_MPESA_CONSUMER_SECRET=your-secret
VORTE_MPESA_SHORTCODE=174379
VORTE_MPESA_PASSKEY=your-passkey
VORTE_MPESA_CALLBACK_URL=https://yourapp.com/api/mpesa/callback
```

## CLI Setup

```bash
vorte mpesa:setup      # Interactive credential setup wizard
vorte mpesa:balance    # Check account balance
```

## Operations

### STK Push (Lipa Na M-Pesa Online)

Initiate payment from a customer's phone:

```python
# Customer receives an STK push prompt on their phone
# They enter their PIN to complete payment
```

### C2B (Customer to Business)

Register URLs for customer-initiated payments.

### B2C (Business to Customer)

Send money from your business to customers.

### B2B (Business to Business)

Transfer funds between businesses.

### Account Balance

Check your M-Pesa account balance.

### Transaction Status

Query the status of a transaction.

## Environments

- **Sandbox** -- For development and testing
- **Production** -- Live transactions

## Testing

Use the `MpesaMocker` for testing without hitting the Daraja API:

```python
from vorte.testing import MpesaMocker

mpesa = MpesaMocker()
mpesa.stk_push_success(receipt="RKT123", checkout_request_id="ws123")
mpesa.stk_push_failure(error="Insufficient funds")

# B2C mocking
mpesa.b2c.send(amount=1000, phone="254712345678")
mpesa.b2c.bulk(payments=[...])
```
