import pytest
from fastapi import Request
from vorte.core.router import (
    VorteAPIRouter,
    VersioningMiddleware,
    VersioningStrategy,
    VersionedRoute,
)

def test_vorte_api_router_registration():
    """Test that routes added via VorteAPIRouter register versioning metadata."""
    router = VorteAPIRouter(prefix="/items", tags=["items"])
    
    async def sample_endpoint():
        return {"status": "ok"}

    # Add a route with versioning metadata
    router.add_api_route(
        path="/",
        endpoint=sample_endpoint,
        methods=["GET", "POST"],
        version="v2",
        deprecated_in="v2.1",
        removed_in="v3",
        sunset_date="2026-12-31T23:59:59Z",
    )

    # Should register two versioned routes (one for GET, one for POST)
    assert len(router._versioned_routes) == 2
    
    route_get = next(r for r in router._versioned_routes if r.method == "GET")
    assert route_get.path == "/"
    assert route_get.version == "v2"
    assert route_get.deprecated_in == "v2.1"
    assert route_get.removed_in == "v3"
    assert route_get.sunset_date == "2026-12-31T23:59:59Z"
    assert "items" in route_get.tags

    route_post = next(r for r in router._versioned_routes if r.method == "POST")
    assert route_post.path == "/"
    assert route_post.version == "v2"
    assert route_post.deprecated_in == "v2.1"


def test_versioning_middleware_parsing_url():
    """Test parsing version from path with URL strategy."""
    mw = VersioningMiddleware(default_version="v1", strategy=VersioningStrategy.URL)
    mw.register_version("v2")

    # Helper function to create a dummy request
    def make_request(path: str) -> Request:
        scope = {
            "type": "http",
            "path": path,
            "headers": [],
        }
        return Request(scope)

    # Case 1: URL contains version
    req1 = make_request("/api/v2/users")
    assert mw.parse_version(req1) == "v2"

    # Case 2: URL contains a different version
    req2 = make_request("/v3/items")
    assert mw.parse_version(req2) == "v3"

    # Case 3: URL doesn't contain a version (should return default_version)
    req3 = make_request("/api/users")
    assert mw.parse_version(req3) == "v1"


def test_versioning_middleware_parsing_header():
    """Test parsing version from headers with HEADER strategy."""
    mw = VersioningMiddleware(default_version="v1", strategy=VersioningStrategy.HEADER)
    mw.register_version("v2")

    def make_request(headers: list) -> Request:
        scope = {
            "type": "http",
            "path": "/api/users",
            "headers": headers,
        }
        return Request(scope)

    # Case 1: Header API-Version is provided
    req1 = make_request([(b"api-version", b"v2")])
    assert mw.parse_version(req1) == "v2"

    # Case 2: Header is missing (should return default_version)
    req2 = make_request([])
    assert mw.parse_version(req2) == "v1"


def test_deprecation_and_sunset_headers():
    """Test registering deprecations and getting deprecation headers."""
    mw = VersioningMiddleware()
    
    mw.register_deprecation(
        path="/api/v1/old-endpoint",
        deprecated_in="v1.5",
        removed_in="v2.0",
        sunset_date="2026-06-30T00:00:00Z",
        alternative_path="/api/v2/new-endpoint",
    )

    # Fetch headers for the deprecated route
    headers = mw.get_deprecation_headers("/api/v1/old-endpoint")
    assert headers is not None
    assert headers["Deprecation"] == "true"
    assert headers["Sunset"] == "2026-06-30T00:00:00Z"
    assert headers["Link"] == '</api/v2/new-endpoint>; rel="successor-version"'

    # Fetch headers for a non-deprecated route (should return None)
    assert mw.get_deprecation_headers("/api/v1/active-endpoint") is None
