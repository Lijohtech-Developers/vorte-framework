"""
Vorte Cache Layer 3 - Edge CDN Cache Abstraction
=================================================
Abstraction for edge/CDN caching using purge APIs. Supports
Cloudflare, Fastly, AWS CloudFront, or a custom CDN adapter.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vorte.cache.l3")


@dataclass
class CDNCacheEntry:
    """Metadata about a CDN-cached resource."""
    url: str
    cache_key: str
    tags: List[str] = field(default_factory=list)
    ttl: int = 0
    surrogate_key: Optional[str] = None


class CDNAdapter(ABC):
    """Abstract interface for a CDN provider adapter."""

    @abstractmethod
    async def purge(self, urls: List[str]) -> Dict[str, Any]:
        """Purge specific URLs from the CDN."""
        ...

    @abstractmethod
    async def purge_by_tag(self, tag: str) -> Dict[str, Any]:
        """Purge all resources tagged with a given tag."""
        ...

    @abstractmethod
    async def purge_all(self) -> Dict[str, Any]:
        """Purge all cached resources (site-wide)."""
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check CDN connectivity."""
        ...


class NullCDNAdapter(CDNAdapter):
    """
    No-op CDN adapter used when no CDN is configured.
    All operations succeed silently without doing anything.
    """

    async def purge(self, urls: List[str]) -> Dict[str, Any]:
        return {"status": "ok", "purged": len(urls), "adapter": "null"}

    async def purge_by_tag(self, tag: str) -> Dict[str, Any]:
        return {"status": "ok", "tag": tag, "adapter": "null"}

    async def purge_all(self) -> Dict[str, Any]:
        return {"status": "ok", "adapter": "null"}

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "available", "adapter": "null"}


class CloudflareAdapter(CDNAdapter):
    """
    Cloudflare CDN adapter using the Cache Purge API.

    Requires:
        - ``CLOUDFLARE_ZONE_ID`` and ``CLOUDFLARE_API_TOKEN`` environment
          variables, or passing them directly.
    """

    def __init__(
        self,
        zone_id: Optional[str] = None,
        api_token: Optional[str] = None,
        base_url: str = "https://api.cloudflare.com/client/v4",
    ):
        import os
        self._zone_id = zone_id or os.environ.get("CLOUDFLARE_ZONE_ID", "")
        self._api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN", "")
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, body: Optional[Dict] = None) -> Dict[str, Any]:
        """Make an HTTP request to the Cloudflare API."""
        import json
        from urllib.request import Request, urlopen

        url = f"{self._base_url}/zones/{self._zone_id}{path}"
        data = json.dumps(body).encode() if body else None
        req = Request(url, data=data, headers=self._headers, method=method)

        try:
            async def _do():
                import asyncio
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, lambda: urlopen(req).read().decode()
                )

            raw = await _do()
            return json.loads(raw)
        except Exception as exc:
            logger.error("Cloudflare API error: %s", exc)
            return {"success": False, "errors": [str(exc)]}

    async def purge(self, urls: List[str]) -> Dict[str, Any]:
        return await self._request("POST", "/purge_cache", {"files": urls})

    async def purge_by_tag(self, tag: str) -> Dict[str, Any]:
        return await self._request("POST", "/purge_cache", {"tags": [tag]})

    async def purge_all(self) -> Dict[str, Any]:
        return await self._request("POST", "/purge_cache", {"purge_everything": True})

    async def health_check(self) -> Dict[str, Any]:
        if not self._zone_id or not self._api_token:
            return {"status": "unconfigured", "adapter": "cloudflare"}
        result = await self._request("GET", "")
        return {
            "status": "healthy" if result.get("success") else "unhealthy",
            "adapter": "cloudflare",
        }


class L3CDNCache:
    """
    Edge CDN cache abstraction (L3).

    This layer does **not** store data locally — it manages the
    relationship between cache keys and CDN resources, and provides
    purge/invalidation operations against the CDN provider's API.

    Typical use-cases:
        - Purging HTML/API responses cached at the edge
        - Surrogate-key-based cache invalidation
        - Tag-based bulk purging (e.g., invalidate all ``user:42`` pages)

    Args:
        adapter: A :class:`CDNAdapter` instance. Defaults to :class:`NullCDNAdapter`.
        base_url: The public base URL used to construct full URLs for purge operations.

    Usage:
        cdn = L3CDNCache(adapter=CloudflareAdapter(), base_url="https://api.example.com")
        cdn.track("user:42", "/api/v1/users/42", tags=["users", "user:42"])
        await cdn.invalidate("user:42")
    """

    def __init__(
        self,
        adapter: Optional[CDNAdapter] = None,
        base_url: str = "",
    ):
        self._adapter = adapter or NullCDNAdapter()
        self._base_url = base_url.rstrip("/")
        # Local index: cache_key -> CDNCacheEntry
        self._entries: Dict[str, CDNCacheEntry] = {}
        # Tag index: tag -> set of cache keys
        self._tag_index: Dict[str, set] = {}
        self._hits: int = 0
        self._misses: int = 0

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------

    def track(
        self,
        cache_key: str,
        path: str,
        tags: Optional[List[str]] = None,
        ttl: int = 0,
        surrogate_key: Optional[str] = None,
    ) -> None:
        """
        Register a CDN-cached resource so it can be purged later.

        Args:
            cache_key: Logical cache key used by the framework.
            path: URL path of the cached resource.
            tags: Tags for grouped invalidation.
            ttl: TTL hint (informational, actual TTL is CDN-managed).
            surrogate_key: Optional surrogate key for Fastly-style purging.
        """
        full_url = f"{self._base_url}{path}" if self._base_url else path
        entry = CDNCacheEntry(
            url=full_url,
            cache_key=cache_key,
            tags=tags or [],
            ttl=ttl,
            surrogate_key=surrogate_key,
        )
        # Remove old entry
        if cache_key in self._entries:
            old = self._entries[cache_key]
            for tag in old.tags:
                self._tag_index.get(tag, set()).discard(cache_key)

        self._entries[cache_key] = entry

        for tag in entry.tags:
            self._tag_index.setdefault(tag, set()).add(cache_key)

    def untrack(self, cache_key: str) -> None:
        """Stop tracking a cache key."""
        entry = self._entries.pop(cache_key, None)
        if entry:
            for tag in entry.tags:
                tag_keys = self._tag_index.get(tag)
                if tag_keys:
                    tag_keys.discard(cache_key)
                    if not tag_keys:
                        del self._tag_index[tag]

    # ------------------------------------------------------------------
    # Invalidation (calls the CDN provider)
    # ------------------------------------------------------------------

    async def invalidate(self, cache_key: str) -> Dict[str, Any]:
        """
        Purge a single cached resource from the CDN.

        Returns the CDN purge response.
        """
        entry = self._entries.get(cache_key)
        if entry is None:
            self._misses += 1
            return {"status": "not_found", "key": cache_key}

        self._hits += 1
        result = await self._adapter.purge([entry.url])
        self.untrack(cache_key)
        return result

    async def invalidate_tag(self, tag: str) -> Dict[str, Any]:
        """
        Purge all cached resources with a given tag.

        Tries the CDN's native tag purge first, then falls back
        to individual URL purges.
        """
        tag_keys = self._tag_index.get(tag, set())
        if not tag_keys:
            return {"status": "not_found", "tag": tag}

        # Try native tag purge
        cdn_result = await self._adapter.purge_by_tag(tag)

        # Also untrack local entries
        for key in list(tag_keys):
            self.untrack(key)

        return {
            **cdn_result,
            "keys_invalidated": len(tag_keys),
        }

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate resources whose cache_key matches a glob pattern.

        Falls back to individual URL purges since most CDNs do not
        natively support glob purges.

        Args:
            pattern: Glob pattern (e.g., ``"user:*"``).

        Returns:
            Number of keys purged.
        """
        import fnmatch
        matching = [k for k in self._entries if fnmatch.fnmatch(k, pattern)]
        if not matching:
            return 0

        urls = [self._entries[k].url for k in matching]
        await self._adapter.purge(urls)

        for key in matching:
            self.untrack(key)

        return len(matching)

    async def purge_all(self) -> Dict[str, Any]:
        """Purge all cached resources (site-wide)."""
        result = await self._adapter.purge_all()
        self._entries.clear()
        self._tag_index.clear()
        return result

    # ------------------------------------------------------------------
    # Statistics & health
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return CDN cache statistics."""
        return {
            "layer": "l3_cdn",
            "tracked_entries": len(self._entries),
            "tracked_tags": len(self._tag_index),
            "hits": self._hits,
            "misses": self._misses,
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check CDN adapter health."""
        return await self._adapter.health_check()
