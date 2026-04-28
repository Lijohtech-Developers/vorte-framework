"""
Vorte Cache Layer 2 - Distributed Redis Cache
=============================================
Distributed Redis-backed cache layer for cross-process and
cross-server caching with TTL, tagging, and pattern-based
invalidation using Redis SCAN.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

from vorte.core.config import RedisConfig

logger = logging.getLogger("vorte.cache.l2")


class L2RedisCache:
    """
    Distributed Redis cache (L2) with TTL and tag-based invalidation.

    This layer sits behind the in-process L1 cache and provides shared
    caching across multiple workers or servers.  It requires a Redis
    instance but delivers sub-millisecond latency for cached reads.

    Features:
        - Per-key TTL
        - Tag-based invalidation via Redis SET membership
        - Glob-pattern key scanning for invalidation
        - JSON serialization for complex values
        - Graceful fallback when Redis is unavailable
        - Connection health checks
        - Pipeline support for bulk operations

    Args:
        redis_url: Redis connection URL.
        prefix: Key prefix namespace (avoids collisions with other data).
        default_ttl: Default TTL in seconds.

    Usage:
        cache = L2RedisCache("redis://localhost:6379/1")
        cache.set("user:42", {"name": "Alice"}, ttl=600, tags=["users"])
        data = cache.get("user:42")
        cache.invalidate_tag("users")
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "vorte:cache:",
        default_ttl: int = 300,
    ):
        self._url = redis_url
        self._prefix = prefix
        self._default_ttl = default_ttl
        self._client: Optional[Any] = None
        self._available: bool = False
        # Statistics
        self._hits: int = 0
        self._misses: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """
        Establish the Redis connection.

        Uses ``redis.asyncio`` when available, falling back to a
        synchronous ``redis.Redis`` wrapped in a simple async shim.
        """
        try:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(
                self._url, decode_responses=True, socket_connect_timeout=5
            )
            await self._client.ping()
            self._available = True
            logger.info("L2 Redis cache connected to %s", self._url)
        except ImportError:
            logger.warning(
                "redis.asyncio not installed; falling back to sync redis client"
            )
            try:
                import redis
                self._client = redis.from_url(
                    self._url, decode_responses=True, socket_connect_timeout=5
                )
                self._client.ping()
                self._available = True
                logger.info("L2 Redis cache connected (sync) to %s", self._url)
            except Exception as exc:
                logger.error("L2 Redis cache unavailable: %s", exc)
                self._available = False
        except Exception as exc:
            logger.error("L2 Redis cache connection failed: %s", exc)
            self._available = False

    async def disconnect(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            try:
                if hasattr(self._client, "aclose"):
                    await self._client.aclose()
                elif hasattr(self._client, "close"):
                    self._client.close()
            except Exception as exc:
                logger.warning("L2 Redis disconnect error: %s", exc)
            finally:
                self._client = None
                self._available = False

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _key(self, key: str) -> str:
        """Namespace a raw key with the configured prefix."""
        return f"{self._prefix}{key}"

    def _tag_key(self, tag: str) -> str:
        """Return the Redis SET key used to track members of a tag."""
        return f"{self._prefix}__tag:{tag}"

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value by key.

        Returns the deserialized value, or None if missing/expired.
        """
        if not self._available:
            self._misses += 1
            return None

        try:
            raw = await self._execute("GET", self._key(key))
            if raw is None:
                self._misses += 1
                return None

            entry = json.loads(raw)
            # Check TTL
            expires_at = entry.get("expires_at", 0)
            if expires_at > 0 and time.time() > expires_at:
                await self.delete(key)
                self._misses += 1
                return None

            self._hits += 1
            return entry.get("value")
        except Exception as exc:
            logger.warning("L2 Redis GET error for key '%s': %s", key, exc)
            self._misses += 1
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Store a value with optional TTL and tags.

        Args:
            key: Cache key.
            value: Value to store (must be JSON-serializable).
            ttl: Time-to-live in seconds.
            tags: List of tags for grouped invalidation.
        """
        if not self._available:
            return

        try:
            effective_ttl = ttl if ttl is not None else self._default_ttl
            expires_at = time.time() + effective_ttl if effective_ttl > 0 else 0

            entry = json.dumps({
                "value": value,
                "expires_at": expires_at,
                "created_at": time.time(),
            })

            redis_key = self._key(key)

            # Build pipeline: set value + register tags
            pipe_commands: List[tuple] = [
                ("SET", redis_key, entry, "EX", effective_ttl if effective_ttl > 0 else 0)
            ]

            if tags:
                for tag in tags:
                    pipe_commands.append(
                        ("SADD", self._tag_key(tag), redis_key)
                    )

            await self._execute_pipeline(pipe_commands)
        except Exception as exc:
            logger.warning("L2 Redis SET error for key '%s': %s", key, exc)

    async def delete(self, key: str) -> bool:
        """Delete a single key. Returns True if it existed."""
        if not self._available:
            return False

        try:
            result = await self._execute("DEL", self._key(key))
            return bool(result)
        except Exception as exc:
            logger.warning("L2 Redis DEL error for key '%s': %s", key, exc)
            return False

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    async def invalidate(self, key: str) -> bool:
        """Invalidate a single key. Alias for delete."""
        return await self.delete(key)

    async def invalidate_tag(self, tag: str) -> int:
        """
        Invalidate all keys associated with a tag.

        Scans the Redis SET for the tag and removes each member key.

        Args:
            tag: Tag name.

        Returns:
            Number of keys removed.
        """
        if not self._available:
            return 0

        try:
            tag_key = self._tag_key(tag)
            members = await self._execute("SMEMBERS", tag_key)
            if not members:
                return 0

            # Build pipeline: delete all member keys + delete tag set
            pipe_commands = []
            for member in members:
                pipe_commands.append(("DEL", member))
            pipe_commands.append(("DEL", tag_key))

            results = await self._execute_pipeline(pipe_commands)
            # Count non-zero DEL results (every other result, except last)
            return sum(1 for r in results[:-1] if r)
        except Exception as exc:
            logger.warning("L2 Redis invalidate_tag error for '%s': %s", tag, exc)
            return 0

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a glob pattern using SCAN.

        Args:
            pattern: Glob pattern applied after the prefix, e.g. ``"user:*"``.

        Returns:
            Number of keys removed.
        """
        if not self._available:
            return 0

        try:
            full_pattern = self._prefix + pattern
            cursor = 0
            keys_to_delete: List[str] = []
            while True:
                cursor, keys = await self._execute("SCAN", cursor, "MATCH", full_pattern, "COUNT", 100)
                keys_to_delete.extend(keys)
                cursor = int(cursor)
                if cursor == 0:
                    break

            if not keys_to_delete:
                return 0

            # Delete in batches of 100 to avoid blocking
            count = 0
            for i in range(0, len(keys_to_delete), 100):
                batch = keys_to_delete[i : i + 100]
                pipe_commands = [("DEL", *batch)]
                results = await self._execute_pipeline(pipe_commands)
                count += sum(results)
            return count
        except Exception as exc:
            logger.warning("L2 Redis invalidate_pattern error for '%s': %s", pattern, exc)
            return 0

    async def clear(self) -> None:
        """Remove all keys with the configured prefix (DANGEROUS in production)."""
        if not self._available:
            return

        try:
            await self.invalidate_pattern("*")
            logger.info("L2 Redis cache cleared for prefix '%s'", self._prefix)
        except Exception as exc:
            logger.warning("L2 Redis clear error: %s", exc)

    # ------------------------------------------------------------------
    # Warmup
    # ------------------------------------------------------------------

    async def warmup(
        self, entries: Dict[str, Any], ttl: Optional[int] = None
    ) -> int:
        """
        Pre-populate the cache with entries via pipeline.

        Args:
            entries: Mapping of key -> value.
            ttl: TTL for each entry.

        Returns:
            Number of entries loaded.
        """
        if not self._available or not entries:
            return 0

        try:
            effective_ttl = ttl if ttl is not None else self._default_ttl
            expires_at = time.time() + effective_ttl if effective_ttl > 0 else 0
            pipe_commands = []
            for key, value in entries.items():
                entry = json.dumps({
                    "value": value,
                    "expires_at": expires_at,
                    "created_at": time.time(),
                })
                pipe_commands.append((
                    "SET",
                    self._key(key),
                    entry,
                    "EX",
                    effective_ttl if effective_ttl > 0 else 0,
                ))

            await self._execute_pipeline(pipe_commands)
            return len(entries)
        except Exception as exc:
            logger.warning("L2 Redis warmup error: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Statistics & health
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "layer": "l2_redis",
            "available": self._available,
            "url": self._url,
            "prefix": self._prefix,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 2),
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check Redis connectivity."""
        if not self._available:
            return {"status": "unavailable"}

        try:
            pong = await self._execute("PING")
            return {"status": "healthy", "ping": pong}
        except Exception as exc:
            self._available = False
            return {"status": "unhealthy", "error": str(exc)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute(self, command: str, *args) -> Any:
        """Execute a single Redis command."""
        if self._client is None:
            return None
        if hasattr(self._client, command.lower()):
            method = getattr(self._client, command.lower())
            return await method(*args)
        raise RuntimeError(f"Unknown Redis command: {command}")

    async def _execute_pipeline(self, commands: List[tuple]) -> List[Any]:
        """Execute a batch of Redis commands in a pipeline."""
        if self._client is None or not commands:
            return []

        # Check if the client supports async pipelines
        if hasattr(self._client, "pipeline"):
            pipe = self._client.pipeline()
            for cmd in commands:
                name = cmd[0]
                args = cmd[1:]
                getattr(pipe, name.lower())(*args)
            results = await pipe.execute()
            return results

        # Fallback: execute sequentially
        results = []
        for cmd in commands:
            result = await self._execute(cmd[0], *cmd[1:])
            results.append(result)
        return results
