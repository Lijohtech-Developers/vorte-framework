"""
Vorte Cache Layer 1 - In-Process Memory Cache
=============================================
Dict-based, in-process memory cache with per-key TTL support,
LRU eviction, and tag-based grouping. This is the fastest cache
layer as it requires no network I/O.
"""

from __future__ import annotations

import fnmatch
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class _CacheEntry:
    """A single cache entry with TTL tracking."""
    value: Any
    expires_at: float
    tags: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    hit_count: int = 0
    size_bytes: int = 0


class L1MemoryCache:
    """
    In-process memory cache (L1) with TTL and LRU eviction.

    This is the fastest cache layer — data lives in the current
    process's memory. Ideal for small, frequently-accessed values
    such as configuration lookups, session fragments, or computed
    hot paths.

    Features:
        - Per-key TTL (time-to-live)
        - LRU eviction when max_size is reached
        - Tag-based grouping for bulk invalidation
        - Thread-safe operations
        - Glob-pattern key matching for invalidation
        - Cache warmup support
        - Hit/miss statistics

    Args:
        max_size: Maximum number of entries before LRU eviction kicks in.
        default_ttl: Default time-to-live in seconds (0 = no expiry).

    Usage:
        cache = L1MemoryCache(max_size=500, default_ttl=60)
        cache.set("user:42", {"name": "Alice"}, ttl=120, tags=["users"])
        data = cache.get("user:42")
        cache.invalidate_tag("users")
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._tag_index: Dict[str, Set[str]] = {}  # tag -> set of keys
        self._lock = threading.RLock()
        # Statistics
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value by key. Returns None if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.expires_at > 0 and time.time() > entry.expires_at:
                self._remove_entry(key)
                self._misses += 1
                return None

            # LRU: move to end (most recently used)
            self._store.move_to_end(key)
            entry.hit_count += 1
            self._hits += 1
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Store a value with an optional TTL and tags.

        Args:
            key: Cache key.
            value: Value to store (must be picklable for serialization elsewhere).
            ttl: Time-to-live in seconds. Uses default_ttl if None.
            tags: List of tags for grouped invalidation.
        """
        with self._lock:
            # Evict if necessary (before insertion to stay within budget)
            if key not in self._store:
                self._evict_if_needed()

            # Remove old entry if overwriting
            if key in self._store:
                self._remove_entry(key)

            effective_ttl = ttl if ttl is not None else self._default_ttl
            expires_at = time.time() + effective_ttl if effective_ttl > 0 else 0

            tag_set: Set[str] = set(tags) if tags else set()
            entry = _CacheEntry(
                value=value,
                expires_at=expires_at,
                tags=tag_set,
                size_bytes=self._estimate_size(value),
            )
            self._store[key] = entry

            # Update tag index
            for tag in tag_set:
                self._tag_index.setdefault(tag, set()).add(key)

    def delete(self, key: str) -> bool:
        """
        Delete a single key. Returns True if the key existed.

        Args:
            key: Cache key to remove.
        """
        with self._lock:
            if key in self._store:
                self._remove_entry(key)
                return True
            return False

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate(self, key: str) -> bool:
        """Invalidate a single key. Alias for delete."""
        return self.delete(key)

    def invalidate_tag(self, tag: str) -> int:
        """
        Invalidate all keys associated with a tag.

        Args:
            tag: Tag name to invalidate.

        Returns:
            Number of keys removed.
        """
        with self._lock:
            keys = self._tag_index.pop(tag, set())
            count = 0
            for key in keys:
                if key in self._store:
                    self._remove_entry(key)
                    count += 1
            return count

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., ``"user:*"`` or ``"session:*"``).

        Returns:
            Number of keys removed.
        """
        with self._lock:
            keys_to_remove = [
                k for k in self._store.keys() if fnmatch.fnmatch(k, pattern)
            ]
            for key in keys_to_remove:
                self._remove_entry(key)
            return len(keys_to_remove)

    def clear(self) -> None:
        """Remove all entries and reset statistics."""
        with self._lock:
            self._store.clear()
            self._tag_index.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    # ------------------------------------------------------------------
    # Warmup
    # ------------------------------------------------------------------

    def warmup(self, entries: Dict[str, Any], ttl: Optional[int] = None) -> int:
        """
        Pre-populate the cache with entries.

        Args:
            entries: Mapping of key -> value to load.
            ttl: TTL for warmup entries (uses default_ttl if None).

        Returns:
            Number of entries loaded.
        """
        count = 0
        for key, value in entries.items():
            self.set(key, value, ttl=ttl)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            return {
                "layer": "l1_memory",
                "size": len(self._store),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate_pct": round(hit_rate, 2),
                "tags": len(self._tag_index),
            }

    def keys(self) -> List[str]:
        """Return a list of all non-expired keys."""
        with self._lock:
            now = time.time()
            return [
                k for k, v in self._store.items()
                if v.expires_at == 0 or now <= v.expires_at
            ]

    def has(self, key: str) -> bool:
        """Check whether a key exists and is not expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            if entry.expires_at > 0 and time.time() > entry.expires_at:
                self._remove_entry(key)
                return False
            return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _remove_entry(self, key: str) -> None:
        """Remove an entry and its tag associations. Caller must hold the lock."""
        entry = self._store.pop(key, None)
        if entry is None:
            return
        for tag in entry.tags:
            tag_keys = self._tag_index.get(tag)
            if tag_keys is not None:
                tag_keys.discard(key)
                if not tag_keys:
                    del self._tag_index[tag]

    def _evict_if_needed(self) -> None:
        """Evict expired entries first, then LRU entries until within budget."""
        # First pass: remove expired
        now = time.time()
        expired_keys = [
            k for k, v in self._store.items()
            if v.expires_at > 0 and now > v.expires_at
        ]
        for key in expired_keys:
            self._remove_entry(key)
            self._evictions += 1

        if len(self._store) < self._max_size:
            return

        # Second pass: evict LRU (oldest) entries
        while len(self._store) >= self._max_size:
            key, _ = self._store.popitem(last=False)
            self._evictions += 1

    @staticmethod
    def _estimate_size(value: Any) -> int:
        """Rough byte-size estimate for an in-memory value."""
        import sys
        return sys.getsizeof(value)
