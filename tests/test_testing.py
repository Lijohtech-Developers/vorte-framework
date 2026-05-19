import pytest
from pydantic import BaseModel, Field
from vorte import Vorte, success_response, error_response
from vorte.testing import (
    VorteTestClient,
    TestResponse,
    AIMocker,
    MpesaMocker,
    VorteTestCase,
)

class SampleSchema(BaseModel):
    id: int
    name: str
    active: bool = True


@pytest.mark.asyncio
async def test_test_client_and_assertions():
    """Test VorteTestClient and its custom TestResponse assertions."""
    app = Vorte(auto_load=False)
    
    @app.get("/api/ok")
    async def get_ok():
        return success_response(data={"id": 123, "name": "Vorte Test", "active": True})

    @app.post("/api/error")
    async def post_error():
        return error_response(code="BAD_REQUEST", message="Invalid payload", status_code=400)

    async with VorteTestClient(app) as client:
        # Test success response & assertions
        resp = await client.get("/api/ok")
        assert isinstance(resp, TestResponse)
        assert resp.status_code == 200
        assert resp.success is True
        assert resp.data["id"] == 123
        
        # Run standard assertions
        resp.assert_success()
        resp.assert_status(200)
        resp.assert_data({"id": 123, "name": "Vorte Test", "active": True})
        resp.assert_schema(SampleSchema)

        # Test error response & assertions
        resp_err = await client.post("/api/error")
        assert resp_err.status_code == 400
        assert resp_err.success is False
        
        # Run error assertions
        resp_err.assert_error(code="BAD_REQUEST")
        resp_err.assert_status(400)


def test_ai_mocker():
    """Test AIMocker utility for prompt response mocking."""
    mocker = AIMocker()
    
    # Pre-register responses
    mocker.mock_response("Summarize this: Hello world", "Hello summary")
    mocker.mock_default("Default response")
    
    # Query specific mock
    assert mocker.get_response("Summarize this: Hello world") == "Hello summary"
    assert mocker.call_count == 1
    assert mocker.calls[0]["prompt"] == "Summarize this: Hello world"

    # Query default mock
    assert mocker.get_response("Translate: Bonjour") == "Default response"
    assert mocker.call_count == 2

    # Reset mocker
    mocker.reset()
    assert mocker.call_count == 0
    assert len(mocker.calls) == 0
    assert mocker.get_response("Summarize this: Hello world") is None


@pytest.mark.asyncio
async def test_mpesa_mocker():
    """Test MpesaMocker utility for payment simulation."""
    mocker = MpesaMocker()
    
    # Test default STK Push response
    stk_resp = await mocker.stk_push(phone="254712345678", amount=100)
    assert stk_resp["success"] is True
    assert stk_resp["checkout_request_id"] == "ws_CO_TEST"
    assert mocker.stk_push.call_count == 1

    # Pre-register specific STK responses
    mocker.stk_push_success(receipt="ABC123XYZ", checkout_request_id="ws_CO_999")
    mocker.stk_push_failure(error="Insufficient balance")

    # Resolve success
    stk_success = await mocker.stk_push(phone="254712345678", amount=200)
    assert stk_success["success"] is True
    assert stk_success["receipt"] == "ABC123XYZ"
    assert stk_success["checkout_request_id"] == "ws_CO_999"

    # Resolve failure
    stk_fail = await mocker.stk_push(phone="254712345678", amount=300)
    assert stk_fail["success"] is False
    assert stk_fail["error"] == "Insufficient balance"

    # Test B2C mocks
    b2c_resp = await mocker.b2c.send(phone="254712345678", amount=150)
    assert b2c_resp["success"] is True
    assert b2c_resp["receipt"] == "TEST_B2C"

    # Reset mocker
    mocker.reset()
    assert mocker.stk_push.call_count == 0


class TestMyVorteTestCase(VorteTestCase):
    """Integrates and tests the VorteTestCase structure."""
    
    # We define class level app for VorteTestCase setup_class
    app = Vorte(auto_load=False)
    
    @classmethod
    def setup_class(cls):
        # Explicitly register an endpoint on our app before calling super()
        @cls.app.get("/class-route")
        async def class_route():
            return success_response(data="class_response")
            
        super().setup_class()

    @pytest.mark.asyncio
    async def test_class_client_assertions(self):
        """Test assertions inside a class inheriting from VorteTestCase."""
        assert self.client is not None
        
        # Test standard client resolution
        resp = await self.client.get("/class-route")
        self.assert_success(resp)
        assert resp.data == "class_response"
