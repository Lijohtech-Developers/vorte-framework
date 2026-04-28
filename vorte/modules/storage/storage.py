"""
Vorte Storage Module — Storage Manager & Driver Interface
=========================================================
Provides a unified API for file storage: put, get, delete, url, stream, cdn_url.
"""

from __future__ import annotations

import abc
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger("vorte.modules.storage")


class StorageDriver(abc.ABC):
    """Interface every storage driver must implement."""

    @abc.abstractmethod
    async def put(self, path: str, content: bytes, content_type: str = "",
                  metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload content at the given path."""

    @abc.abstractmethod
    async def get(self, path: str) -> bytes:
        """Download content from the given path."""

    @abc.abstractmethod
    async def delete(self, path: str) -> None:
        """Delete the file at the given path."""

    @abc.abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a file exists."""

    @abc.abstractmethod
    async def url(self, path: str) -> str:
        """Return a URL for the file."""

    @abc.abstractmethod
    async def stream(self, path: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """Stream the file content in chunks."""

    async def copy(self, source: str, destination: str) -> None:
        """Copy a file (optional override)."""
        raise NotImplementedError

    async def move(self, source: str, destination: str) -> None:
        """Move a file (optional override)."""
        raise NotImplementedError

    async def size(self, path: str) -> int:
        """Return file size in bytes."""
        raise NotImplementedError

    async def last_modified(self, path: str) -> float:
        """Return last modified timestamp."""
        raise NotImplementedError

    async def list_files(self, prefix: str = "") -> List[str]:
        """List files with an optional prefix."""
        raise NotImplementedError

    async def cdn_url(self, path: str) -> str:
        """Return a CDN URL for the file."""
        return await self.url(path)

    async def presigned_url(self, path: str, expires_in: int = 3600) -> str:
        """Return a presigned URL (optional)."""
        return await self.url(path)

    async def ping(self) -> bool:
        """Check backend connectivity."""
        return True


class StorageManager:
    """
    Unified storage manager that delegates to a pluggable driver.

    Usage::

        manager = StorageManager(driver="local", base_path="uploads")
        await manager.put("avatars/user1.jpg", image_bytes, content_type="image/jpeg")
        url = await manager.url("avatars/user1.jpg")
    """

    def __init__(
        self,
        driver: str = "local",
        bucket: str = "",
        access_key: str = "",
        secret_key: str = "",
        region: str = "us-east-1",
        endpoint_url: str = "",
        cdn_url: str = "",
        local_path: str = "storage/uploads",
        base_url: str = "/files",
        acl: str = "private",
    ) -> None:
        self._driver_name = driver
        self._cdn_url = cdn_url
        self._disk: Optional[StorageDriver] = None

        if driver == "local":
            from vorte.modules.storage.drivers.local import LocalStorageDriver
            self._disk = LocalStorageDriver(base_path=local_path, base_url=base_url)
        elif driver == "s3":
            from vorte.modules.storage.drivers.s3 import S3StorageDriver
            self._disk = S3StorageDriver(
                bucket=bucket, access_key=access_key, secret_key=secret_key,
                region=region, endpoint_url=endpoint_url, cdn_url=cdn_url, acl=acl,
            )
        elif driver == "gcs":
            from vorte.modules.storage.drivers.s3 import S3StorageDriver
            self._disk = S3StorageDriver(
                bucket=bucket, access_key=access_key, secret_key=secret_key,
                region=region, endpoint_url=endpoint_url or f"https://storage.googleapis.com",
                cdn_url=cdn_url, acl=acl,
            )
        elif driver == "cloudinary":
            # Cloudinary can be added as a separate driver; fall back to S3-style for now
            logger.warning("Cloudinary driver is a stub — falling back to local storage")
            from vorte.modules.storage.drivers.local import LocalStorageDriver
            self._disk = LocalStorageDriver(base_path=local_path, base_url=base_url)
        else:
            from vorte.modules.storage.drivers.local import LocalStorageDriver
            self._disk = LocalStorageDriver(base_path=local_path, base_url=base_url)

    @property
    def disk(self) -> StorageDriver:
        if self._disk is None:
            raise RuntimeError("Storage driver not initialised")
        return self._disk

    @property
    def driver_name(self) -> str:
        return self._driver_name

    async def put(self, path: str, content: bytes, content_type: str = "",
                  metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        return await self.disk.put(path, content, content_type, metadata)

    async def get(self, path: str) -> bytes:
        return await self.disk.get(path)

    async def delete(self, path: str) -> None:
        await self.disk.delete(path)

    async def exists(self, path: str) -> bool:
        return await self.disk.exists(path)

    async def url(self, path: str) -> str:
        return await self.disk.url(path)

    async def stream(self, path: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        async for chunk in self.disk.stream(path, chunk_size):
            yield chunk

    async def copy(self, source: str, destination: str) -> None:
        await self.disk.copy(source, destination)

    async def move(self, source: str, destination: str) -> None:
        await self.disk.move(source, destination)

    async def size(self, path: str) -> int:
        return await self.disk.size(path)

    async def list_files(self, prefix: str = "") -> List[str]:
        return await self.disk.list_files(prefix)

    async def cdn_url(self, path: str) -> str:
        if self._cdn_url:
            return f"{self._cdn_url.rstrip('/')}/{path}"
        return await self.disk.cdn_url(path)

    async def presigned_url(self, path: str, expires_in: int = 3600) -> str:
        return await self.disk.presigned_url(path, expires_in)

    async def ping(self) -> bool:
        return await self.disk.ping()
