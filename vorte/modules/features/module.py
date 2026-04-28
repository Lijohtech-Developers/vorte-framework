"""
Vorte Feature Flags Module
===========================
Feature toggles, gradual rollouts, and A/B testing.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from vorte.core.module import Module, ModuleMeta, ModulePriority
from vorte.core.response import success_response
from vorte.modules.auth.guards import IsAdmin


@dataclass
class FeatureFlag:
    name: str
    enabled: bool = True
    rollout_percentage: int = 100
    targeting: Dict[str, Any] = field(default_factory=dict)
    variants: Optional[List[str]] = None  # For A/B testing
    description: str = ""


class FeatureFlagManager:
    """Manages feature flags and A/B tests."""

    def __init__(self):
        self._flags: Dict[str, FeatureFlag] = {}

    def set(
        self,
        name: str,
        enabled: bool = True,
        rollout: int = 100,
        targeting: Optional[Dict[str, Any]] = None,
        variants: Optional[List[str]] = None,
        description: str = "",
    ) -> FeatureFlag:
        flag = FeatureFlag(
            name=name, enabled=enabled, rollout_percentage=rollout,
            targeting=targeting or {}, variants=variants, description=description,
        )
        self._flags[name] = flag
        return flag

    async def enabled(self, name: str, user_id: Optional[str] = None, user_attributes: Optional[Dict] = None) -> bool:
        """Check if a feature flag is enabled for a given user."""
        flag = self._flags.get(name)
        if not flag or not flag.enabled:
            return False

        # If 100% rollout, it's enabled for everyone
        if flag.rollout_percentage >= 100:
            # Check targeting rules
            if flag.targeting and user_attributes:
                return self._check_targeting(flag.targeting, user_attributes)
            return True

        # Rollout based on user_id hash
        if user_id:
            hash_val = int(hashlib.md5(f"{name}:{user_id}".encode()).hexdigest(), 16)
            bucket = (hash_val % 100) + 1
            if bucket <= flag.rollout_percentage:
                return True
            return False

        # No user context - use rollout percentage
        return random.randint(1, 100) <= flag.rollout_percentage

    async def variant(self, name: str, user_id: Optional[str] = None) -> str:
        """Get the A/B test variant for a user. Returns 'control' if not in test."""
        flag = self._flags.get(name)
        if not flag or not flag.enabled or not flag.variants:
            return "control"

        if user_id:
            hash_val = int(hashlib.md5(f"{name}:variant:{user_id}".encode()).hexdigest(), 16)
            idx = hash_val % len(flag.variants)
            return flag.variants[idx]

        return random.choice(flag.variants)

    def _check_targeting(self, targeting: Dict[str, Any], user_attrs: Dict[str, Any]) -> bool:
        """Check if user attributes match targeting rules."""
        for key, value in targeting.items():
            if key in user_attrs:
                if isinstance(value, list):
                    if user_attrs[key] not in value:
                        return False
                elif user_attrs[key] != value:
                    return False
        return True

    def get_flag(self, name: str) -> Optional[FeatureFlag]:
        return self._flags.get(name)

    def list_flags(self) -> List[Dict]:
        return [
            {"name": f.name, "enabled": f.enabled, "rollout": f.rollout_percentage,
             "variants": f.variants, "description": f.description}
            for f in self._flags.values()
        ]

    def delete_flag(self, name: str) -> bool:
        return self._flags.pop(name, None) is not None


class FeaturesModule(Module):
    """
    Feature flag module with toggles, rollouts, and A/B testing.
    
    Usage:
        app.register(FeaturesModule())
        if await flags.enabled('new_ai_model', user_id=user.id):
            ...
    """

    meta = ModuleMeta(
        name="features",
        version="1.0.0",
        description="Feature flags, gradual rollouts, and A/B testing",
        priority=ModulePriority.ROUTES,
    )

    def __init__(self):
        super().__init__()
        self.manager: Optional[FeatureFlagManager] = None

    def register(self, app) -> None:
        self.manager = FeatureFlagManager()
        if hasattr(app, 'container'):
            app.container.register_instance(FeatureFlagManager, self.manager)

        router = APIRouter(prefix="/features", tags=["Feature Flags"])

        @router.get("/")
        async def list_flags(user=Depends(IsAdmin)):
            return success_response(self.manager.list_flags())

        @router.post("/{name}")
        async def set_flag(name: str, request: dict, user=Depends(IsAdmin)):
            flag = self.manager.set(name, **request)
            return success_response({"name": flag.name, "enabled": flag.enabled})

        @router.delete("/{name}")
        async def delete_flag(name: str, user=Depends(IsAdmin)):
            ok = self.manager.delete_flag(name)
            return success_response({"deleted": ok})

        app.include_router(router)
