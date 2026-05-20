# Testing Guide

Vorte includes a complete testing framework with an async test client, AI mocker, and M-Pesa mocker.

## VorteTestClient

Async test client using `httpx.AsyncClient` with `ASGITransport`:

```python
import pytest
from vorte import Vorte
from vorte.testing import VorteTestClient

app = Vorte(auto_load=True)

@pytest.fixture
async def client():
    async with VorteTestClient(app) as client:
        yield client
```

### HTTP Methods

```python
response = await client.get("/api/v1/users")
response = await client.post("/api/v1/users", json={"name": "Alice"})
response = await client.put("/api/v1/users/1", json={"name": "Bob"})
response = await client.patch("/api/v1/users/1", json={"email": "bob@ex.com"})
response = await client.delete("/api/v1/users/1")
```

### WebSocket

```python
async with client.websocket("/ws/chat") as ws:
    await ws.send_text("Hello")
    data = await ws.receive_text()
```

## TestResponse

Wrapper around `httpx.Response` with Vorte-specific assertions:

```python
response = await client.get("/api/v1/users")

# Properties
response.status_code   # HTTP status code
response.json_data     # Parsed JSON body
response.data          # "data" field from Vorte envelope
response.success       # "success" field from Vorte envelope
```

### Assertion Methods

All assertions return `self` for chaining:

```python
response.assert_success()                          # Status < 400 and success=True
response.assert_error("NOT_FOUND")                 # Status >= 400, checks error code
response.assert_status(200)                        # Exact status code match
response.assert_data({"id": 1, "name": "Alice"})   # Exact data match
response.assert_schema(UserSchema)                 # Pydantic schema validation
response.assert_ai_usage()                         # Asserts AI metadata exists
```

### Full Example

```python
async def test_create_user(client):
    response = await client.post("/api/v1/users", json={
        "name": "Alice",
        "email": "alice@example.com",
    })
    response.assert_success()
    response.assert_status(201)
    response.assert_schema(UserResponse)
```

## AIMocker

Mock AI calls in tests:

```python
from vorte.testing import AIMocker

ai_mock = AIMocker()

# Mock specific prompts
ai_mock.mock_response("What is Vorte?", {"answer": "An AI framework"})

# Mock default (fallback)
ai_mock.mock_default({"answer": "Generic response"})

# Get mock response
response = ai_mock.get_response("What is Vorte?")
# {"answer": "An AI framework"}

# Track calls
print(ai_mock.call_count)  # 1
print(ai_mock.calls)       # [{"prompt": "What is Vorte?", "response": ...}]

# Reset
ai_mock.reset()
```

## MpesaMocker

Mock M-Pesa API calls in tests:

```python
from vorte.testing import MpesaMocker

mpesa = MpesaMocker()

# Mock successful STK Push
mpesa.stk_push_success(
    receipt="RKT123456",
    checkout_request_id="ws_CO_123",
)

# Mock failed STK Push
mpesa.stk_push_failure(error="Insufficient funds")

# Mock B2C payments
mpesa.b2c.send(amount=1000, phone="254712345678")
mpesa.b2c.bulk(payments=[
    {"amount": 500, "phone": "254712345678"},
    {"amount": 300, "phone": "254712345679"},
])

# Reset
mpesa.reset()
```

## VorteTestCase

Class-based test harness:

```python
from vorte.testing import VorteTestCase

class TestUserAPI(VorteTestCase):
    app = Vorte(auto_load=True)

    def test_list_users(self):
        response = self.client.get("/api/v1/users")
        self.assert_success(response)

    def test_create_user(self):
        response = self.client.post("/api/v1/users", json={
            "name": "Alice",
        })
        self.assert_success(response)
        self.assert_schema(response, UserSchema)
```

The base class provides:
- `self.app` -- The Vorte application
- `self.client` -- VorteTestClient instance
- `self.ai_mock` -- AIMocker instance
- `self.mpesa_mock` -- MpesaMocker instance
- `self.assert_success(response)` -- Success assertion
- `self.assert_error(response, code)` -- Error assertion
- `self.assert_schema(response, schema)` -- Schema assertion

## Running Tests

```bash
# Run all tests
pytest

# Run specific file
pytest tests/test_app.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=vorte
```

Vorte uses `pytest-asyncio` with `asyncio_mode = "auto"` configured in `pyproject.toml`.

## Test Configuration

From `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```
