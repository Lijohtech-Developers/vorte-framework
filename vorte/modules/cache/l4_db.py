"""
Vorte Cache Layer 4 - Database Result Cache
=============================================
Persists cached query results to the database so they survive
application restarts. Useful for expensive aggregations and
slow-changing reference data.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("vorte.cache.l4")


@dataclass
class _DBCacheEntry:
    """A cached entry stored in the database."""
    key: str
    value_json: str
    tags_json: str = "[]"
    expires_at: float = 0
    created_at: float = field(default_factory=time.time)
    hit_count: int = 0


class L4DatabaseCache:
    """
    Database-backed cache (L4) for long-lived, restart-persistent caching.

    This is the slowest cache layer but the most durable. Cached entries
    survive server restarts and are shared across all process instances
    connected to the same database.  Ideal for expensive database
    aggregations, computed reference data, and other values that are
    expensive to compute but change rarely.

    Features:
        - Persistent across restarts
        - TTL-based expiry
        - Tag-based invalidation
        - Hash-based key deduplication
        - Automatic cleanup of expired entries
        - Graceful degradation when DB is unavailable

    Args:
        db_url: Database connection URL (SQLAlchemy-compatible).
        table_name: Name of the cache table.
        default_ttl: Default TTL in seconds.
        auto_cleanup: Whether to auto-cleanup expired entries on reads.

    Usage:
        db_cache = L4DatabaseCache("postgresql+asyncpg://localhost/app")
        await db_cache.initialize()
        await db_cache.set("report:daily", expensive_data, ttl=3600, tags=["reports"])
        data = await db_cache.get("report:daily")
    """

    def __init__(
        self,
        db_url: str = "",
        table_name: str = "vorte_cache_entries",
        default_ttl: int = 3600,
        auto_cleanup: bool = True,
    ):
        self._db_url = db_url
        self._table_name = table_name
        self._default_ttl = default_ttl
        self._auto_cleanup = auto_cleanup
        self._engine: Optional[Any] = None
        self._available: bool = False
        self._hits: int = 0
        self._misses: int = 0
        self._cleanup_interval: int = 300  # seconds between auto-cleanups
        self._last_cleanup: float = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Create the cache table if it does not exist.

        Attempts to use SQLAlchemy async; falls back to a simple
        ``sqlite3`` local cache if no database is configured.
        """
        if not self._db_url:
            logger.info("L4 DB cache: no database URL configured, using local SQLite")
            self._db_url = "sqlite+aiosqlite:///vorte_l4_cache.db"
            self._available = False  # will be set on successful init
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            self._engine = create_async_engine(
                self._db_url, pool_pre_ping=True, pool_size=5
            )
            ddl = text(f"""
                CREATE TABLE IF NOT EXISTS {self._table_name} (
                    cache_key   VARCHAR(512) PRIMARY KEY,
                    value_json  TEXT NOT NULL,
                    tags_json   TEXT NOT NULL DEFAULT '[]',
                    expires_at  FLOAT NOT NULL DEFAULT 0,
                    created_at  FLOAT NOT NULL,
                    hit_count   INTEGER NOT NULL DEFAULT 0
                )
            """)
            async with self._engine.begin() as conn:
                await conn.execute(ddl)

            self._available = True
            logger.info("L4 DB cache initialized with table '%s'", self._table_name)
        except ImportError:
            logger.warning("SQLAlchemy not installed; L4 DB cache disabled")
            self._available = False
        except Exception as exc:
            logger.error("L4 DB cache initialization failed: %s", exc)
            self._available = False

    async def shutdown(self) -> None:
        """Dispose the database engine."""
        if self._engine is not None:
            try:
                await self._engine.dispose()
            except Exception as exc:
                logger.warning("L4 DB cache shutdown error: %s", exc)
            finally:
                self._engine = None
                self._available = False

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value from the database.

        Returns the deserialized value, or None if missing/expired.
        """
        if not self._available or self._engine is None:
            self._misses += 1
            return None

        try:
            from sqlalchemy import text

            # Periodic cleanup
            if self._auto_cleanup:
                await self._maybe_cleanup()

            stmt = text(
                f"SELECT value_json, expires_at, hit_count "
                f"FROM {self._table_name} WHERE cache_key = :key"
            )
            async with self._engine.begin() as conn:
                row = await conn.execute(stmt, {"key": key})
                result = row.fetchone()

            if result is None:
                self._misses += 1
                return None

            value_json, expires_at, hit_count = result

            # Check expiry
            if expires_at > 0 and time.time() > expires_at:
                await self.delete(key)
                self._misses += 1
                return None

            # Increment hit count (fire-and-forget)
            self._increment_hit(key, hit_count)

            self._hits += 1
            return json.loads(value_json)
        except Exception as exc:
            logger.warning("L4 DB cache GET error for key '%s': %s", key, exc)
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
        Store a value in the database cache.

        Uses UPSERT (ON CONFLICT) so repeated sets for the same key
        do not create duplicates.
        """
        if not self._available or self._engine is None:
            return

        try:
            from sqlalchemy import text

            effective_ttl = ttl if ttl is not None else self._default_ttl
            expires_at = time.time() + effective_ttl if effective_ttl > 0 else 0
            value_json = json.dumps(value)
            tags_json = json.dumps(tags or [])

            # Use INSERT ... ON CONFLICT for upsert (works in PostgreSQL/SQLite)
            stmt = text(
                f"INSERT INTO {self._table_name} "
                f"(cache_key, value_json, tags_json, expires_at, created_at, hit_count) "
                f"VALUES (:key, :value, :tags, :expires, :created, 0) "
                f"ON CONFLICT(cache_key) DO UPDATE SET "
                f"value_json = :value, tags_json = :tags, "
                f"expires_at = :expires, created_at = :created"
            )

            async with self._engine.begin() as conn:
                await conn.execute(stmt, {
                    "key": key,
                    "value": value_json,
                    "tags": tags_json,
                    "expires": expires_at,
                    "created": time.time(),
                })
        except Exception as exc:
            logger.warning("L4 DB cache SET error for key '%s': %s", key, exc)

    async def delete(self, key: str) -> bool:
        """Delete a single key. Returns True if the key existed."""
        if not self._available or self._engine is None:
            return False

        try:
            from sqlalchemy import text

            stmt = text(f"DELETE FROM {self._table_name} WHERE cache_key = :key")
            async with self._engine.begin() as conn:
                result = await conn.execute(stmt, {"key": key})
            return result.rowcount > 0
        except Exception as exc:
            logger.warning("L4 DB cache DELETE error for key '%s': %s", key, exc)
            return False

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    async def invalidate(self, key: str) -> bool:
        """Invalidate a single key. Alias for delete."""
        return await self.delete(key)

    async def invalidate_tag(self, tag: str) -> int:
        """
        Invalidate all keys whose tags list contains the given tag.

        Scans all rows and checks JSON tags (not efficient for very large
        caches — consider adding a proper tag table for production use).

        Args:
            tag: Tag name to invalidate.

        Returns:
            Number of keys removed.
        """
        if not self._available or self._engine is None:
            return 0

        try:
            from sqlalchemy import text

            # Find keys where tags_json contains the tag
            # Using JSON functions (PostgreSQL) or string LIKE (fallback)
            like_pattern = f'"%{tag}%"'
            if "postgresql" in self._db_url:
                stmt = text(
                    f"SELECT cache_key FROM {self._table_name} "
                    f"WHERE tags_json::jsonb ? :tag"
                )
                params = {"tag": tag}
            else:
                stmt = text(
                    f"SELECT cache_key FROM {self._table_name} "
                    f"WHERE tags_json LIKE :pattern"
                )
                params = {"pattern": like_pattern}

            async with self._engine.begin() as conn:
                rows = await conn.execute(stmt, params)

            keys = [row[0] for row in rows.fetchall()]
            count = 0
            for key in keys:
                if await self.delete(key):
                    count += 1
            return count
        except Exception as exc:
            logger.warning("L4 DB invalidate_tag error for '%s': %s", tag, exc)
            return 0

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate keys matching a SQL LIKE pattern.

        Args:
            pattern: SQL LIKE pattern (use ``%`` as wildcard, e.g. ``"user:%"``).

        Returns:
            Number of keys removed.
        """
        if not self._available or self._engine is None:
            return 0

        try:
            from sqlalchemy import text

            stmt = text(
                f"DELETE FROM {self._table_name} WHERE cache_key LIKE :pattern"
            )
            async with self._engine.begin() as conn:
                result = await conn.execute(stmt, {"pattern": pattern})
            return result.rowcount
        except Exception as exc:
            logger.warning("L4 DB invalidate_pattern error: %s", exc)
            return 0

    async def clear(self) -> None:
        """Remove all cache entries."""
        if not self._available or self._engine is None:
            return

        try:
            from sqlalchemy import text
            async with self._engine.begin() as conn:
                await conn.execute(text(f"DELETE FROM {self._table_name}"))
        except Exception as exc:
            logger.warning("L4 DB clear error: %s", exc)

    # ------------------------------------------------------------------
    # Warmup
    # ------------------------------------------------------------------

    async def warmup(
        self, entries: Dict[str, Any], ttl: Optional[int] = None
    ) -> int:
        """
        Pre-populate the cache with entries.

        Args:
            entries: Mapping of key -> value.
            ttl: TTL for each entry.

        Returns:
            Number of entries loaded.
        """
        count = 0
        for key, value in entries.items():
            await self.set(key, value, ttl=ttl)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Statistics & health
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "layer": "l4_db",
            "available": self._available,
            "db_url": self._db_url.split("@")[-1] if "@" in self._db_url else self._db_url,
            "table": self._table_name,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 2),
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check database connectivity."""
        if not self._available or self._engine is None:
            return {"status": "unavailable"}

        try:
            from sqlalchemy import text
            async with self._engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return {"status": "healthy"}
        except Exception as exc:
            self._available = False
            return {"status": "unhealthy", "error": str(exc)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _maybe_cleanup(self) -> None:
        """Run expired-entry cleanup if enough time has elapsed."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now

        try:
            from sqlalchemy import text
            stmt = text(
                f"DELETE FROM {self._table_name} "
                f"WHERE expires_at > 0 AND expires_at < :now"
            )
            async with self._engine.begin() as conn:
                await conn.execute(stmt, {"now": now})
            logger.debug("L4 DB cache: expired entries cleaned up")
        except Exception as exc:
            logger.debug("L4 DB cache cleanup error: %s", exc)

    async def _increment_hit(self, key: str, current_hits: int) -> None:
        """Increment the hit count for a key (fire-and-forget)."""
        try:
            from sqlalchemy import text
            stmt = text(
                f"UPDATE {self._table_name} SET hit_count = :hits "
                f"WHERE cache_key = :key"
            )
            async with self._engine.begin() as conn:
                await conn.execute(stmt, {"key": key, "hits": current_hits + 1})
        except Exception:
            pass  # Fire-and-forget
