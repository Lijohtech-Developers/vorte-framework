"""
Vorte Testing Framework
========================
Test client, AI mocking, M-Pesa simulation, and schema validation helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel


class VorteTestClient:
    """Test client for Vorte applications with standard response support."""

    def __init__(self, app):
        self._client = httpx.AsyncClient(
            app=app,
            base_url="http://testserver",
            headers={"Content-Type": "application/json"},
        )

    async def get(self, path: str, **kwargs) -> "TestResponse":
        resp = await self._client.get(path, **kwargs)
        return TestResponse(resp)

    async def post(self, path: str, json: Any = None, **kwargs) -> "TestResponse":
        resp = await self._client.post(path, json=json, **kwargs)
        return TestResponse(resp)

    async def put(self, path: str, json: Any = None, **kwargs) -> "TestResponse":
        resp = await self._client.put(path, json=json, **kwargs)
        return TestResponse(resp)

    async def patch(self, path: str, json: Any = None, **kwargs) -> "TestResponse":
        resp = await self._client.patch(path, json=json, **kwargs)
        return TestResponse(resp)

    async def delete(self, path: str, **kwargs) -> "TestResponse":
        resp = await self._client.delete(path, **kwargs)
        return TestResponse(resp)

    async def websocket(self, path: str) -> Any:
        return self._client.websocket_connect(path)

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


@dataclass
class TestResponse:
    """Wrapper around httpx response with Vorte-specific assertions."""
    _response: httpx.Response = field(repr=False)
    _json: Optional[Dict] = field(default=None, repr=False)

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def json_data(self) -> Dict:
        if self._json is None:
            self._json = self._response.json()
        return self._json

    @property
    def data(self) -> Any:
        """Get the 'data' field from standard Vorte response."""
        return self.json_data.get("data")

    @property
    def success(self) -> bool:
        """Check if the response indicates success."""
        return self.json_data.get("success", False)

    def assert_success(self, msg: str = "Expected success response"):
        assert self.status_code < 400, f"{msg}: {self.json_data}"
        assert self.success, f"{msg}: {self.json_data}"
        return self

    def assert_error(self, code: str = None, msg: str = "Expected error response"):
        assert self.status_code >= 400, f"{msg}: {self.json_data}"
        if code:
            assert self.json_data.get("error", {}).get("code") == code, f"Expected error code '{code}': {self.json_data}"
        return self

    def assert_status(self, expected: int, msg: str = ""):
        assert self.status_code == expected, f"{msg}: Expected {expected}, got {self.status_code}"
        return self

    def assert_data(self, expected: Any, msg: str = ""):
        assert self.data == expected, f"{msg}: Expected {expected}, got {self.data}"
        return self

    def assert_schema(self, schema: Type[BaseModel], msg: str = ""):
        """Validate response data against a Pydantic schema."""
        try:
            schema.model_validate(self.data)
        except Exception as e:
            raise AssertionError(f"{msg}: Schema validation failed: {e}")
        return self

    def assert_ai_usage(self, msg: str = ""):
        """Assert that the response contains AI usage metadata."""
        assert "ai" in self.json_data, f"{msg}: No AI metadata in response"
        return self


class AIMocker:
    """Mocks AI calls in test mode."""

    def __init__(self):
        self._responses: Dict[str, Any] = {}
        self._call_count = 0
        self._calls: List[Dict[str, Any]] = []

    def mock_response(self, prompt: str, response: Any):
        """Register a mock response for a prompt."""
        self._responses[prompt] = response

    def mock_default(self, response: Any):
        """Register a default mock response."""
        self._responses["__default__"] = response

    def get_response(self, prompt: str) -> Optional[Any]:
        self._call_count += 1
        self._calls.append({"prompt": prompt, "timestamp": __import__('time').time()})
        return self._responses.get(prompt, self._responses.get("__default__"))

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def calls(self) -> List[Dict]:
        return list(self._calls)

    def reset(self):
        self._responses.clear()
        self._call_count = 0
        self._calls.clear()


class MpesaMocker:
    """Mocks M-Pesa API calls in test mode."""

    def __init__(self):
        self._stk_push_results: List[Dict] = []
        self._stk_push_calls: List[Dict] = []
        self._b2c_results: List[Dict] = []

    def stk_push_success(self, receipt: str = "TEST123", checkout_request_id: str = "ws_CO_123456"):
        self._stk_push_results.append({"success": True, "receipt": receipt, "checkout_request_id": checkout_request_id})

    def stk_push_failure(self, error: str = "STK Push failed"):
        self._stk_push_results.append({"success": False, "error": error})

    @property
    def stk_push(self):
        return _StkPushMock(self)

    @property
    def b2c(self):
        return _B2CMock(self)

    def reset(self):
        self._stk_push_results.clear()
        self._stk_push_calls.clear()
        self._b2c_results.clear()


class _StkPushMock:
    def __init__(self, mocker: MpesaMocker):
        self._mocker = mocker

    async def __call__(self, phone: str, amount: int, **kwargs):
        self._mocker._stk_push_calls.append({"phone": phone, "amount": amount})
        if self._mocker._stk_push_results:
            return self._mocker._stk_push_results.pop(0)
        return {"success": True, "checkout_request_id": "ws_CO_TEST"}

    @property
    def call_count(self) -> int:
        return len(self._mocker._stk_push_calls)


class _B2CMock:
    def __init__(self, mocker: MpesaMocker):
        self._mocker = mocker

    async def send(self, phone: str, amount: int, **kwargs):
        return {"success": True, "receipt": "TEST_B2C"}

    async def bulk(self, items: List[Dict]):
        return {"success": True, "count": len(items)}


class VorteTestCase:
    """Base test case class for Vorte applications."""

    app = None
    client: VorteTestClient = None
    ai_mock: AIMocker = AIMocker()
    mpesa_mock: MpesaMocker = MpesaMocker()

    @classmethod
    def setup_class(cls):
        if cls.app:
            cls.client = VorteTestClient(cls.app)

    @classmethod
    def teardown_class(cls):
        if cls.client:
            import asyncio
            asyncio.get_event_loop().run_until_complete(cls.client.close())

    def assert_success(self, response: TestResponse, msg: str = ""):
        response.assert_success(msg)

    def assert_error(self, response: TestResponse, code: str = None, msg: str = ""):
        response.assert_error(code, msg)

    def assert_schema(self, response: TestResponse, schema: Type[BaseModel]):
        response.assert_schema(schema)
