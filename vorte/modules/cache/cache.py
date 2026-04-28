"""
Vorte Cache Manager
====================
Multi-layer cache orchestrator that coordinates reads/writes across
all four cache layers (L1 memory → L2 Redis → L3 CDN → L4 database).

Read path: L1 → L2 → L4 → miss (L3 is CDN-only, not a read store).
Write path: L1 + L2 + L4 (all layers), L3 tracked for invalidation.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union

from vorte.core.config import CacheConfig

from .l1_memory import L1MemoryCache
from .l2_redis import L2RedisCache
from .l3_cdn import L3CDNCache
from .l4_db import L4DatabaseCache

logger = logging.getLogger("vorte.cache")

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


class CacheLayer(str, Enum):
    """Cache layer identifiers."""
    MEMORY = "memory"
    REDIS = "redis"
    CDN = "cdn"
    DATABASE = "database"
    ALL = "all"


# Map string names to enum values
_LAYER_MAP = {
    "memory": CacheLayer.MEMORY,
    "l1": CacheLayer.MEMORY,
    "redis": CacheLayer.REDIS,
    "l2": CacheLayer.REDIS,
    "cdn": CacheLayer.CDN,
    "l3": CacheLayer.CDN,
    "database": CacheLayer.DATABASE,
    "db": CacheLayer.DATABASE,
    "l4": CacheLayer.DATABASE,
}


def parse_layer(layer: Union[str, CacheLayer, None]) -> Optional[CacheLayer]:
    """Parse a layer specifier string/enum into a CacheLayer."""
    if layer is None:
        return None
    if isinstance(layer, CacheLayer):
        return layer
    return _LAYER_MAP.get(layer.lower())


class CacheManager:
    """
    Multi-layer cache manager that orchestrates reads and writes
    across four cache layers.

    Architecture::

        ┌─────────────────────────────────────────────┐
        │                 Application                  │
        └──────────────────┬──────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │ CacheManager│
                    └──┬────┬────┬──┘
                       │    │    │
              ┌────────▼┐ ┌▼────▼──────┐ ┌───────────┐
              │  L1:     │ │ L2: Redis  │ │ L4: DB    │
              │  Memory  │ │            │ │           │
              └──────────┘ └────────────┘ └───────────┘
                                              L3: CDN (invalidate-only)

    Read path (cascading):
        1. L1 in-process memory (fastest)
        2. L2 Redis (distributed)
        3. L4 Database (persistent)
        If a value is found in a deeper layer, it is back-filled
        into shallower layers.

    Write path (broadcast):
        A write propagates to L1, L2, and L4 simultaneously.
        L3 tracks the key for later CDN purge.

    Args:
        config: Cache configuration.

    Usage:
        cache = CacheManager(CacheConfig())
        await cache.initialize()

        # Direct usage
        await cache.set("user:42", data, ttl=300, tags=["users"])
        data = await cache.get("user:42")

        # Decorator usage
        @cache.cached(ttl=60, tags=["users"])
        async def get_user(user_id: int):
            return await db.fetch_user(user_id)
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        config = config or CacheConfig()
        self._default_ttl = config.default_ttl

        # L1: In-process memory cache
        self.l1: L1MemoryCache = L1MemoryCache(
            max_size=config.l1_max_size,
            default_ttl=config.default_ttl,
        ) if config.l1_enabled else None

        # L2: Redis cache
        self.l2: Optional[L2RedisCache] = None
        if config.l2_enabled:
            redis_url = config.l3_cdn_url or ""  # Reuse if not separate
            self.l2 = L2RedisCache(
                redis_url="redis://localhost:6379/0",
                default_ttl=config.default_ttl,
            )

        # L3: CDN cache (invalidate-only)
        self.l3: L3CDNCache = L3CDNCache(base_url="")

        # L4: Database cache
        self.l4: Optional[L4DatabaseCache] = None
        if config.l4_db_cache:
            self.l4 = L4DatabaseCache(default_ttl=config.default_ttl)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Initialize all cache layers (connect to external services)."""
        tasks = []
        if self.l2:
            tasks.append(self.l2.connect())
        if self.l4:
            tasks.append(self.l4.initialize())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("CacheManager initialized (L1=%s, L2=%s, L3=cdn, L4=%s)",
                     self.l1 is not None, self.l2 is not None, self.l4 is not None)

    async def shutdown(self) -> None:
        """Shutdown all cache layers gracefully."""
        tasks = []
        if self.l2:
            tasks.append(self.l2.disconnect())
        if self.l4:
            tasks.append(self.l4.shutdown())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self.l1:
            self.l1.clear()

        logger.info("CacheManager shutdown complete")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value by key, cascading through layers.

        Read order: L1 → L2 → L4 → None.
        When a value is found in a deeper layer, it is back-filled
        into shallower layers for faster future access.
        """
        # L1: Memory
        if self.l1 is not None:
            value = self.l1.get(key)
            if value is not None:
                return value

        # L2: Redis
        if self.l2 is not None:
            value = await self.l2.get(key)
            if value is not None:
                # Back-fill L1
                if self.l1 is not None:
                    self.l1.set(key, value, ttl=self._default_ttl)
                return value

        # L4: Database
        if self.l4 is not None:
            value = await self.l4.get(key)
            if value is not None:
                # Back-fill L1 and L2
                if self.l1 is not None:
                    self.l1.set(key, value, ttl=self._default_ttl)
                if self.l2 is not None:
                    await self.l2.set(key, value, ttl=self._default_ttl)
                return value

        return None

    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        Retrieve multiple values by key.

        Args:
            keys: List of cache keys.

        Returns:
            Dict of found key -> value pairs.
        """
        results = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                results[key] = value
        return results

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
        layer: Optional[Union[str, CacheLayer]] = None,
    ) -> None:
        """
        Store a value across cache layers.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time-to-live in seconds.
            tags: Tags for grouped invalidation.
            layer: Target layer only, or ``None`` for all layers.
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl
        target = parse_layer(layer)

        # L1
        if (target is None or target == CacheLayer.MEMORY) and self.l1 is not None:
            self.l1.set(key, value, ttl=effective_ttl, tags=tags)

        # L2
        if (target is None or target == CacheLayer.REDIS) and self.l2 is not None:
            await self.l2.set(key, value, ttl=effective_ttl, tags=tags)

        # L3: Track for CDN invalidation (not a data store)
        if (target is None or target == CacheLayer.CDN) and tags:
            self.l3.track(key, f"/cache/{key}", tags=tags, ttl=effective_ttl)

        # L4
        if (target is None or target == CacheLayer.DATABASE) and self.l4 is not None:
            await self.l4.set(key, value, ttl=effective_ttl, tags=tags)

    async def set_many(
        self,
        entries: Dict[str, Any],
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> int:
        """
        Store multiple values across all cache layers.

        Args:
            entries: Mapping of key -> value.
            ttl: TTL for each entry.
            tags: Tags for each entry.

        Returns:
            Number of entries stored.
        """
        count = 0
        for key, value in entries.items():
            await self.set(key, value, ttl=ttl, tags=tags)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Deletion & Invalidation
    # ------------------------------------------------------------------

    async def delete(self, key: str, layer: Optional[Union[str, CacheLayer]] = None) -> None:
        """
        Delete a key from one or all layers.

        Args:
            key: Cache key to delete.
            layer: Target layer only, or ``None`` for all layers.
        """
        target = parse_layer(layer)

        if (target is None or target == CacheLayer.MEMORY) and self.l1 is not None:
            self.l1.delete(key)

        if (target is None or target == CacheLayer.REDIS) and self.l2 is not None:
            await self.l2.delete(key)

        if (target is None or target == CacheLayer.CDN):
            await self.l3.invalidate(key)

        if (target is None or target == CacheLayer.DATABASE) and self.l4 is not None:
            await self.l4.delete(key)

    async def invalidate(self, key: str) -> None:
        """Invalidate a key across all layers."""
        await self.delete(key)

    async def invalidate_tag(self, tag: str) -> Dict[str, int]:
        """
        Invalidate all keys with a tag across all layers.

        Args:
            tag: Tag name to invalidate.

        Returns:
            Dict with counts per layer.
        """
        results: Dict[str, int] = {}

        if self.l1 is not None:
            results["l1"] = self.l1.invalidate_tag(tag)

        if self.l2 is not None:
            results["l2"] = await self.l2.invalidate_tag(tag)

        cdn_result = await self.l3.invalidate_tag(tag)
        if cdn_result.get("keys_invalidated"):
            results["l3"] = cdn_result["keys_invalidated"]

        if self.l4 is not None:
            results["l4"] = await self.l4.invalidate_tag(tag)

        return results

    async def invalidate_pattern(self, pattern: str) -> Dict[str, int]:
        """
        Invalidate all keys matching a pattern across all layers.

        Args:
            pattern: Glob pattern (L1/L2/L3) or SQL LIKE pattern (L4).

        Returns:
            Dict with counts per layer.
        """
        results: Dict[str, int] = {}

        if self.l1 is not None:
            results["l1"] = self.l1.invalidate_pattern(pattern)

        if self.l2 is not None:
            results["l2"] = await self.l2.invalidate_pattern(pattern)

        l3_count = await self.l3.invalidate_pattern(pattern)
        if l3_count:
            results["l3"] = l3_count

        if self.l4 is not None:
            # Convert glob to SQL LIKE for L4
            sql_pattern = pattern.replace("*", "%").replace("?", "_")
            results["l4"] = await self.l4.invalidate_pattern(sql_pattern)

        return results

    async def clear(self) -> None:
        """Clear all layers."""
        if self.l1 is not None:
            self.l1.clear()
        if self.l2 is not None:
            await self.l2.clear()
        if self.l4 is not None:
            await self.l4.clear()
        await self.l3.purge_all()

    # ------------------------------------------------------------------
    # Warmup
    # ------------------------------------------------------------------

    async def warmup(self, entries: Dict[str, Any], ttl: Optional[int] = None) -> Dict[str, int]:
        """
        Pre-populate all cache layers with entries.

        Args:
            entries: Mapping of key -> value.
            ttl: TTL for each entry.

        Returns:
            Dict with load counts per layer.
        """
        results: Dict[str, int] = {}

        if self.l1 is not None:
            results["l1"] = self.l1.warmup(entries, ttl=ttl)

        if self.l2 is not None:
            results["l2"] = await self.l2.warmup(entries, ttl=ttl)

        if self.l4 is not None:
            results["l4"] = await self.l4.warmup(entries, ttl=ttl)

        return results

    # ------------------------------------------------------------------
    # Decorator
    # ------------------------------------------------------------------

    def cached(
        self,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
        key_prefix: Optional[str] = None,
        layer: Optional[Union[str, CacheLayer]] = None,
    ) -> Callable[[F], F]:
        """
        Decorator to cache function results.

        The cache key is derived from the function name and arguments.

        Args:
            ttl: Cache TTL in seconds.
            tags: Tags for invalidation.
            key_prefix: Custom key prefix (defaults to function module.name).
            layer: Target cache layer (default: all).

        Usage:
            @cache.cached(ttl=300, tags=["users"])
            async def get_user(user_id: int):
                return await db.fetch_user(user_id)
        """
        def decorator(func: F) -> F:
            prefix = key_prefix or f"{func.__module__}.{func.__qualname__}"
            is_async = inspect.iscoroutinefunction(func)

            def _build_key(args: tuple, kwargs: dict) -> str:
                """Build a deterministic cache key from function arguments."""
                import hashlib
                import json
                raw = json.dumps({
                    "args": [str(a) for a in args[1:]],  # skip self/cls
                    "kwargs": {k: str(v) for k, v in sorted(kwargs.items())},
                }, sort_keys=True)
                hash_hex = hashlib.md5(raw.encode()).hexdigest()[:12]
                return f"{prefix}:{hash_hex}"

            if is_async:
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    cache_key = _build_key(args, kwargs)
                    result = await self.get(cache_key)
                    if result is not None:
                        return result

                    result = await func(*args, **kwargs)
                    await self.set(cache_key, result, ttl=ttl, tags=tags, layer=layer)
                    return result
                return async_wrapper  # type: ignore
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    # For sync functions, use L1 only (non-blocking)
                    cache_key = _build_key(args, kwargs)
                    if self.l1 is not None:
                        result = self.l1.get(cache_key)
                        if result is not None:
                            return result

                    result = func(*args, **kwargs)
                    if self.l1 is not None:
                        self.l1.set(cache_key, result, ttl=ttl, tags=tags)
                    return result
                return sync_wrapper  # type: ignore

        return decorator

    # ------------------------------------------------------------------
    # Statistics & health
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return statistics from all cache layers."""
        result: Dict[str, Any] = {"layers": {}}
        if self.l1 is not None:
            result["layers"]["l1"] = self.l1.stats()
        if self.l2 is not None:
            result["layers"]["l2"] = self.l2.stats()
        result["layers"]["l3"] = self.l3.stats()
        if self.l4 is not None:
            result["layers"]["l4"] = self.l4.stats()
        return result

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all external cache layers."""
        checks: Dict[str, Any] = {}
        if self.l2 is not None:
            checks["l2_redis"] = await self.l2.health_check()
        if self.l4 is not None:
            checks["l4_db"] = await self.l4.health_check()
        checks["l3_cdn"] = await self.l3.health_check()
        return checks
