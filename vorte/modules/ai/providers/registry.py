"""
Vorte AI Module - Provider Registry
=====================================
Registry, routing, and fallback logic for AI providers.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Type

from vorte.modules.ai.providers.base import BaseProvider
from vorte.modules.ai.schemas import (
    CompletionRequest,
    ProviderConfig,
    RouterStrategy,
)


class ProviderRegistry:
    """
    Central registry for AI providers.

    Responsibilities:
    * Register / unregister providers by name
    * Resolve the correct provider for a given model or request
    * Execute fallback chains on failure
    * Implement routing strategies (round-robin, cost-optimised, …)
    """

    def __init__(self) -> None:
        self._providers: Dict[str, BaseProvider] = {}
        self._model_to_provider: Dict[str, str] = {}
        self._fallback_chain: List[str] = []
        self._strategy: RouterStrategy = RouterStrategy.STATIC
        self._round_robin_idx: int = 0
        self._provider_latency: Dict[str, List[float]] = defaultdict(list)
        self._provider_costs: Dict[str, float] = defaultdict(float)
        self._provider_load: Dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, provider: BaseProvider) -> None:
        """Register a provider instance."""
        self._providers[provider.name] = provider
        # Map each known model to this provider
        if provider.config.models:
            for model in provider.config.models:
                self._model_to_provider[model] = provider.name

    def unregister(self, name: str) -> None:
        """Remove a provider by name."""
        if name in self._providers:
            del self._providers[name]

    def get(self, name: str) -> Optional[BaseProvider]:
        """Get a registered provider by name."""
        return self._providers.get(name)

    def get_all(self) -> Dict[str, BaseProvider]:
        return dict(self._providers)

    @property
    def provider_names(self) -> List[str]:
        return list(self._providers.keys())

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def set_strategy(self, strategy: RouterStrategy) -> None:
        self._strategy = strategy

    def set_fallback_chain(self, chain: List[str]) -> None:
        self._fallback_chain = chain

    def resolve_provider(
        self,
        request: CompletionRequest,
    ) -> BaseProvider:
        """
        Resolve the *best* provider for a given request.

        Resolution order:
        1. Explicit ``request.provider`` name
        2. Model-to-provider mapping
        3. Routing strategy
        """
        # 1 – Explicit provider
        if request.provider and request.provider in self._providers:
            return self._providers[request.provider]

        # 2 – Model mapping
        if request.model and request.model in self._model_to_provider:
            return self._providers[self._model_to_provider[request.model]]

        # 3 – Strategy-based routing
        return self._route_by_strategy(request)

    def _route_by_strategy(self, request: CompletionRequest) -> BaseProvider:
        """Pick a provider based on the configured routing strategy."""
        available = list(self._providers.values())
        if not available:
            raise RuntimeError("No AI providers registered.")
        if len(available) == 1:
            return available[0]

        if self._strategy == RouterStrategy.ROUND_ROBIN:
            provider = available[self._round_robin_idx % len(available)]
            self._round_robin_idx += 1
            return provider

        if self._strategy == RouterStrategy.COST_OPTIMIZED:
            return min(available, key=lambda p: self._provider_costs.get(p.name, 0.0))

        if self._strategy == RouterStrategy.LEAST_LOADED:
            return min(available, key=lambda p: self._provider_load.get(p.name, 0))

        if self._strategy == RouterStrategy.LATENCY_OPTIMIZED:
            def _avg_latency(p: BaseProvider) -> float:
                history = self._provider_latency.get(p.name, [])
                return (sum(history) / len(history)) if history else float("inf")
            return min(available, key=_avg_latency)

        if self._strategy == RouterStrategy.QUALITY_FIRST:
            # Prefer providers that host "larger" models
            quality_order = {"anthropic": 0, "openai": 1, "gemini": 2, "mistral": 3}
            available.sort(key=lambda p: quality_order.get(p.name, 99))
            return available[0]

        # STATIC – return the first registered provider
        return available[0]

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def get_fallback_chain(self, exclude: Optional[str] = None) -> List[BaseProvider]:
        """Return an ordered list of fallback providers."""
        chain: List[BaseProvider] = []
        for name in self._fallback_chain:
            if name != exclude and name in self._providers:
                chain.append(self._providers[name])
        # Add any remaining providers not already in the chain
        for name, provider in self._providers.items():
            if name != exclude and provider not in chain:
                chain.append(provider)
        return chain

    # ------------------------------------------------------------------
    # Telemetry (latency / cost tracking used by routing)
    # ------------------------------------------------------------------

    def record_latency(self, provider_name: str, latency_s: float) -> None:
        history = self._provider_latency[provider_name]
        history.append(latency_s)
        # Keep a sliding window of the last 100 measurements
        if len(history) > 100:
            del history[:-100]

    def record_cost(self, provider_name: str, cost: float) -> None:
        self._provider_costs[provider_name] += cost

    def increment_load(self, provider_name: str) -> None:
        self._provider_load[provider_name] += 1

    def decrement_load(self, provider_name: str) -> None:
        self._provider_load[provider_name] = max(0, self._provider_load[provider_name] - 1)

    # ------------------------------------------------------------------
    # Built-in provider classes (lazy import to avoid circular deps)
    # ------------------------------------------------------------------

    _builtin_providers: Dict[str, str] = {
        "openai": "vorte.modules.ai.providers.openai.OpenAIProvider",
        "anthropic": "vorte.modules.ai.providers.anthropic.AnthropicProvider",
        "gemini": "vorte.modules.ai.providers.gemini.GeminiProvider",
        "mistral": "vorte.modules.ai.providers.mistral.MistralProvider",
    }

    @classmethod
    def get_provider_class(cls, name: str) -> Type[BaseProvider]:
        """Import and return the provider class for *name*."""
        dotted = cls._builtin_providers.get(name)
        if not dotted:
            raise ValueError(f"Unknown provider: {name!r}. "
                             f"Available: {list(cls._builtin_providers)}")
        import importlib
        mod_path, cls_name = dotted.rsplit(".", 1)
        mod = importlib.import_module(mod_path)
        return getattr(mod, cls_name)
