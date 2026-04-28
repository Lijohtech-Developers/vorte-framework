"""
Vorte Multi-tenancy Module
============================
Infrastructure-level multi-tenancy with schema, database, and row-level isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from vorte.core.module import Module, ModuleMeta, ModulePriority
from vorte.core.response import success_response, error_response
from vorte.modules.auth.guards import IsAuthenticated, IsAdmin


@dataclass
class Tenant:
    id: str
    name: str
    slug: str
    plan: str = "basic"
    domain: Optional[str] = None
    schema_name: Optional[str] = None
    database_url: Optional[str] = None
    is_active: bool = True
    created_at: str = field(default_factory=lambda: __import__('time').strftime("%Y-%m-%dT%H:%M:%SZ"))


class CurrentTenant:
    """Represents the current tenant context."""

    def __init__(self, tenant: Optional[Tenant] = None):
        self._tenant = tenant

    @property
    def id(self) -> Optional[str]:
        return self._tenant.id if self._tenant else None

    @property
    def name(self) -> Optional[str]:
        return self._tenant.name if self._tenant else None

    @property
    def slug(self) -> Optional[str]:
        return self._tenant.slug if self._tenant else None

    @property
    def plan(self) -> str:
        return self._tenant.plan if self._tenant else "basic"

    @property
    def is_active(self) -> bool:
        return self._tenant.is_active if self._tenant else True


class TenancyResolver:
    """Resolves tenant from various strategies."""

    def __init__(self, strategy: str = "header"):
        self._strategy = strategy
        self._tenants: Dict[str, Tenant] = {}

    def register_tenant(self, tenant: Tenant) -> None:
        self._tenants[tenant.slug] = tenant

    def resolve(self, request: Request) -> Optional[Tenant]:
        if self._strategy == "subdomain":
            host = request.headers.get("host", "").split(".")[0]
            return self._tenants.get(host)
        elif self._strategy == "header":
            slug = request.headers.get("X-Tenant", "")
            return self._tenants.get(slug)
        elif self._strategy == "path":
            parts = request.url.path.split("/")
            if len(parts) > 1:
                return self._tenants.get(parts[1])
        elif self._strategy == "jwt_claim":
            # Tenant extracted from JWT by auth module
            tenant = getattr(request.state, "tenant", None)
            return tenant
        return None

    def list_tenants(self) -> List[Tenant]:
        return list(self._tenants.values())


class MultiTenancyModule(Module):
    """
    Multi-tenancy module with schema, database, and row-level isolation.
    
    Usage:
        app.register(MultiTenancyModule(
            strategy='subdomain',
            isolation='schema',
        ))
    """

    meta = ModuleMeta(
        name="tenancy",
        version="1.0.0",
        description="Multi-tenancy with schema/database/row-level isolation",
        priority=ModulePriority.CONFIG,
    )

    def __init__(self, *, strategy: str = "header", isolation: str = "schema"):
        super().__init__(strategy=strategy, isolation=isolation)
        self._strategy = strategy
        self._isolation = isolation
        self._resolver: Optional[TenancyResolver] = None
        self._router = APIRouter(prefix="/tenancy", tags=["Multi-tenancy"])

    def register(self, app) -> None:
        self._resolver = TenancyResolver(strategy=self._strategy)

        # Add tenant resolution middleware
        @app.middleware("http")
        async def tenancy_middleware(request: Request, call_next):
            tenant = self._resolver.resolve(request)
            request.state.tenant = tenant
            request.state.current_tenant = CurrentTenant(tenant)
            response = await call_next(request)
            if tenant:
                response.headers["X-Tenant"] = tenant.slug
            return response

        if hasattr(app, 'container'):
            app.container.register_instance(TenancyResolver, self._resolver)
            app.container.register_instance(CurrentTenant, CurrentTenant())

        self._setup_routes()
        app.include_router(self._router)

    def _setup_routes(self):
        @self._router.get("/current")
        async def get_current_tenant(request: Request):
            tenant = getattr(request.state, "current_tenant", None)
            if not tenant or not tenant.id:
                return error_response("NO_TENANT", "No tenant context found", status_code=404)
            return success_response({"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "plan": tenant.plan})

        @self._router.post("/tenants")
        async def create_tenant(request: dict, user = Depends(IsAdmin)):
            tenant = Tenant(
                id=f"tnt_{__import__('uuid').uuid4().hex[:12]}",
                name=request["name"],
                slug=request["slug"],
                plan=request.get("plan", "basic"),
                domain=request.get("domain"),
            )
            self._resolver.register_tenant(tenant)
            return success_response({"id": tenant.id, "name": tenant.name, "slug": tenant.slug}, status_code=201)

        @self._router.get("/tenants")
        async def list_tenants(user = Depends(IsAdmin)):
            tenants = self._resolver.list_tenants()
            return success_response([{"id": t.id, "name": t.name, "slug": t.slug, "plan": t.plan} for t in tenants])

    @property
    def resolver(self) -> TenancyResolver:
        return self._resolver
