import pytest
from pydantic import BaseModel
from vorte import Vorte, success_response, error_response
from vorte.core.response import (
    VorteResponse,
    VorteJSONResponse,
    PaginationMeta,
    AIMeta,
    ErrorDetail,
    paginated_response,
    ai_response,
)
from vorte.testing import VorteTestClient

class ItemModel(BaseModel):
    id: int
    name: str


def test_vorte_response_envelope():
    """Test standard VorteResponse serialization envelope."""
    # Test basic success response
    resp = VorteResponse(success=True, data={"id": 1, "value": "test"})
    dict_data = resp.to_dict()
    assert dict_data["success"] is True
    assert dict_data["data"] == {"id": 1, "value": "test"}
    assert "meta" in dict_data
    assert "request_id" in dict_data["meta"]
    assert "timestamp" in dict_data["meta"]
    assert "error" not in dict_data
    assert "pagination" not in dict_data
    assert "ai" not in dict_data


def test_vorte_response_with_pagination():
    """Test response envelope containing pagination metadata."""
    pag = PaginationMeta.from_offset(page=2, per_page=10, total=45)
    resp = VorteResponse(success=True, data=[1, 2, 3], pagination=pag)
    dict_data = resp.to_dict()
    assert dict_data["success"] is True
    assert dict_data["pagination"]["page"] == 2
    assert dict_data["pagination"]["per_page"] == 10
    assert dict_data["pagination"]["total"] == 45
    assert dict_data["pagination"]["total_pages"] == 5


def test_vorte_response_with_ai_meta():
    """Test response envelope containing AI usage metadata."""
    ai = AIMeta(model="gpt-4o", provider="openai", tokens=150, cost="0.002", response_time_ms=500)
    resp = VorteResponse(success=True, data={"summary": "This is a summary"}, ai=ai)
    dict_data = resp.to_dict()
    assert dict_data["success"] is True
    assert dict_data["ai"]["model"] == "gpt-4o"
    assert dict_data["ai"]["provider"] == "openai"
    assert dict_data["ai"]["tokens"] == 150
    assert dict_data["ai"]["cost"] == "0.002"
    assert dict_data["ai"]["response_time_ms"] == 500


def test_vorte_response_with_error():
    """Test response envelope containing detailed error metadata."""
    err = ErrorDetail(code="VALIDATION_FAILED", message="Invalid input provided", details={"field": "email"}, field="email")
    resp = VorteResponse(success=False, error=err)
    dict_data = resp.to_dict()
    assert dict_data["success"] is False
    assert dict_data["data"] is None
    assert dict_data["error"]["code"] == "VALIDATION_FAILED"
    assert dict_data["error"]["message"] == "Invalid input provided"
    assert dict_data["error"]["details"] == {"field": "email"}
    assert dict_data["error"]["field"] == "email"


def test_response_helpers():
    """Test success_response and error_response helper functions."""
    # Test success helper
    success_resp = success_response(data={"message": "ok"}, status_code=201)
    assert isinstance(success_resp, VorteJSONResponse)
    assert success_resp.status_code == 201
    body = success_resp.init_headers  # To peek at serialized content or similar, wait, let's load body.
    import json
    body_data = json.loads(success_resp.body.decode("utf-8"))
    assert body_data["success"] is True
    assert body_data["data"] == {"message": "ok"}

    # Test error helper
    error_resp = error_response(code="NOT_FOUND", message="Resource not found", status_code=404, details="ID does not exist")
    assert isinstance(error_resp, VorteJSONResponse)
    assert error_resp.status_code == 404
    body_data = json.loads(error_resp.body.decode("utf-8"))
    assert body_data["success"] is False
    assert body_data["error"]["code"] == "NOT_FOUND"
    assert body_data["error"]["message"] == "Resource not found"
    assert body_data["error"]["details"] == "ID does not exist"


def test_extended_helpers():
    """Test paginated_response and ai_response helper functions."""
    # Paginated helper
    pag_resp = paginated_response(data=["a", "b"], page=1, per_page=20, total=100)
    assert isinstance(pag_resp, VorteJSONResponse)
    import json
    body_data = json.loads(pag_resp.body.decode("utf-8"))
    assert body_data["success"] is True
    assert body_data["data"] == ["a", "b"]
    assert body_data["pagination"]["total"] == 100
    assert body_data["pagination"]["total_pages"] == 5

    # AI helper
    ai_resp = ai_response(data="Generated text", model="claude-3-opus", provider="anthropic", tokens=100)
    assert isinstance(ai_resp, VorteJSONResponse)
    body_data = json.loads(ai_resp.body.decode("utf-8"))
    assert body_data["success"] is True
    assert body_data["data"] == "Generated text"
    assert body_data["ai"]["model"] == "claude-3-opus"
    assert body_data["ai"]["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_middleware_headers():
    """Test that middleware adds standard envelope headers to responses."""
    app = Vorte(auto_load=False)
    
    @app.get("/test-route")
    async def sample_route():
        return {"value": "hello"}

    async with VorteTestClient(app) as client:
        # Standard route call
        resp = await client.get("/test-route")
        
        # Check standard headers
        assert "X-Request-ID" in resp._response.headers
        assert resp._response.headers["X-Powered-By"] == "Vorte"
        assert "X-Response-Time" in resp._response.headers
        
        # Verify the format of X-Request-ID
        request_id = resp._response.headers["X-Request-ID"]
        assert request_id.startswith("req_")
