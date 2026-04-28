"""
Vorte Cache Decorators
========================
Convenient decorators for caching function return values with
multi-layer support, tag-based invalidation, and TTL control.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import logging
from typing import Any, Callable, List, Optional, TypeVar, Union

from .cache import CacheLayer, CacheManager, parse_layer

logger = logging.getLogger("vorte.cache.decorators")

F = TypeVar("F", bound=Callable[..., Any])


def _default_cache_manager() -> Optional[CacheManager]:
    """Lazily get the global cache manager from the DI container."""
    try:
        from vorte.core.di import _global_container
        return _global_container.resolve(CacheManager)
    except (KeyError, AttributeError):
        return None


def cache(
    *,
    ttl: Optional[int] = None,
    tags: Optional[List[str]] = None,
    key_prefix: Optional[str] = None,
    layer: Optional[Union[str, CacheLayer]] = None,
    cache_manager: Optional[CacheManager] = None,
    condition: Optional[Callable[..., bool]] = None,
) -> Callable[[F], F]:
    """
    Decorator to cache function results in the Vorte multi-layer cache.

    When applied to a function, the return value is cached and subsequent
    calls with the same arguments return the cached value until it expires.

    The cache key is automatically derived from the function's qualified
    name and its arguments (md5-hashed for uniqueness).

    Args:
        ttl: Time-to-live in seconds. Uses the default TTL if not specified.
        tags: List of tags for grouped invalidation. Allows bulk-clearing
              all entries that share a tag (e.g., ``tags=["users"]``).
        key_prefix: Custom key prefix. Defaults to ``module.ClassName.method``.
        layer: Target a specific cache layer (``"memory"``, ``"redis"``,
               ``"database"``, ``"cdn"``) instead of all layers.
        cache_manager: Explicit cache manager instance. If not provided,
              the global CacheManager from the DI container is used.
        condition: Optional callable that receives the same args as the
              decorated function. If it returns ``False``, caching is
              skipped for that invocation.

    Usage:
        from vorte.modules.cache.decorators import cache

        @cache(ttl=300, tags=["users"])
        async def get_user(user_id: int) -> dict:
            return await db.query("SELECT * FROM users WHERE id = $1", user_id)

        # Conditional caching
        @cache(ttl=60, condition=lambda user_id: user_id > 0)
        async def get_user_profile(user_id: int) -> dict:
            ...

        # Specific layer
        @cache(ttl=600, layer="redis", tags=["products"])
        async def get_product(product_id: int) -> dict:
            ...
    """
    def decorator(func: F) -> F:
        _prefix = key_prefix or f"{func.__module__}.{func.__qualname__}"
        _is_async = inspect.iscoroutinefunction(func)

        def _build_key(args: tuple, kwargs: dict) -> str:
            """Build a deterministic cache key from function arguments."""
            raw = json.dumps({
                "args": [repr(a) for a in args[1:]],  # skip self/cls
                "kwargs": {k: repr(v) for k, v in sorted(kwargs.items())},
            }, sort_keys=True, default=str)
            hash_hex = hashlib.sha256(raw.encode()).hexdigest()[:16]
            return f"{_prefix}:{hash_hex}"

        def _get_manager() -> Optional[CacheManager]:
            return cache_manager or _default_cache_manager()

        if _is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                mgr = _get_manager()
                if mgr is None:
                    # No cache manager available — just call the function
                    return await func(*args, **kwargs)

                # Check condition
                if condition is not None and not condition(*args, **kwargs):
                    return await func(*args, **kwargs)

                cache_key = _build_key(args, kwargs)
                result = await mgr.get(cache_key)
                if result is not None:
                    return result

                result = await func(*args, **kwargs)
                await mgr.set(cache_key, result, ttl=ttl, tags=tags, layer=layer)
                return result

            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                mgr = _get_manager()
                if mgr is None:
                    return func(*args, **kwargs)

                if condition is not None and not condition(*args, **kwargs):
                    return func(*args, **kwargs)

                cache_key = _build_key(args, kwargs)

                # For sync functions, try L1 memory only (non-blocking)
                if mgr.l1 is not None:
                    result = mgr.l1.get(cache_key)
                    if result is not None:
                        return result

                result = func(*args, **kwargs)
                if mgr.l1 is not None:
                    mgr.l1.set(cache_key, result, ttl=ttl, tags=tags)
                return result

            return sync_wrapper  # type: ignore

    return decorator


def cache_key(prefix: str, *args: Any, **kwargs: Any) -> str:
    """
    Generate a deterministic cache key from a prefix and arguments.

    This utility is useful when you need to manually build cache keys
    that match what the ``@cache`` decorator would generate.

    Args:
        prefix: Key namespace/prefix.
        *args: Positional arguments to include in the key.
        **kwargs: Keyword arguments to include in the key.

    Returns:
        A cache key string.

    Usage:
        key = cache_key("user:profile", user_id=42)
        # => "user:profile:a1b2c3d4e5f6..."
    """
    raw = json.dumps({
        "args": [repr(a) for a in args],
        "kwargs": {k: repr(v) for k, v in sorted(kwargs.items())},
    }, sort_keys=True, default=str)
    hash_hex = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{prefix}:{hash_hex}"


def warm_on_startup(
    *,
    key_fn: Optional[Callable[..., str]] = None,
    ttl: Optional[int] = None,
    tags: Optional[List[str]] = None,
) -> Callable[[F], F]:
    """
    Decorator that pre-warms the cache on application startup.

    The decorated function is called once during startup and its result
    is stored in the cache. Subsequent calls serve from cache until expiry.

    Args:
        key_fn: Optional callable that returns a cache key.
                Defaults to ``"warmup:{module}.{qualname}"``.
        ttl: Cache TTL in seconds.
        tags: Tags for invalidation.

    Usage:
        @warm_on_startup(ttl=3600, tags=["config", "settings"])
        async def load_feature_flags() -> dict:
            return await db.query("SELECT * FROM feature_flags")
    """
    def decorator(func: F) -> F:
        _is_async = inspect.iscoroutinefunction(func)
        _default_key = f"warmup:{func.__module__}.{func.__qualname__}"

        async def warmup():
            mgr = _default_cache_manager()
            if mgr is None:
                return

            try:
                if _is_async:
                    result = await func()
                else:
                    result = func()

                cache_key = key_fn() if key_fn else _default_key
                await mgr.set(cache_key, result, ttl=ttl, tags=tags)
                logger.info("Cache warmup complete: %s", _default_key)
            except Exception as exc:
                logger.warning("Cache warmup failed for %s: %s", _default_key, exc)

        # Store the warmup function for later invocation
        func._vorte_warmup = warmup  # type: ignore

        if _is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                mgr = _default_cache_manager()
                if mgr is None:
                    return await func(*args, **kwargs)

                cache_key = key_fn() if key_fn else _default_key
                result = await mgr.get(cache_key)
                if result is not None:
                    return result

                result = await func(*args, **kwargs)
                await mgr.set(cache_key, result, ttl=ttl, tags=tags)
                return result

            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                mgr = _default_cache_manager()
                if mgr is None:
                    return func(*args, **kwargs)

                cache_key = key_fn() if key_fn else _default_key
                if mgr.l1 is not None:
                    result = mgr.l1.get(cache_key)
                    if result is not None:
                        return result

                result = func(*args, **kwargs)
                if mgr.l1 is not None:
                    mgr.l1.set(cache_key, result, ttl=ttl, tags=tags)
                return result

            return sync_wrapper  # type: ignore

    return decorator
