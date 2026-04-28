"""
Vorte Cache Module
===================
4-layer caching system: L1 (memory) → L2 (Redis) → L3 (CDN) → L4 (database).
"""

from .module import CacheModule
from .cache import CacheManager, CacheLayer, parse_layer
from .l1_memory import L1MemoryCache
from .l2_redis import L2RedisCache
from .l3_cdn import L3CDNCache, CDNAdapter, CloudflareAdapter, NullCDNAdapter
from .l4_db import L4DatabaseCache
from .decorators import cache, cache_key, warm_on_startup

__all__ = [
    "CacheModule",
    "CacheManager",
    "CacheLayer",
    "parse_layer",
    "L1MemoryCache",
    "L2RedisCache",
    "L3CDNCache",
    "CDNAdapter",
    "CloudflareAdapter",
    "NullCDNAdapter",
    "L4DatabaseCache",
    "cache",
    "cache_key",
    "warm_on_startup",
]
