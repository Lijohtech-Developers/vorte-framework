"""
Vorte Storage Module — Local Filesystem Driver
===============================================
Stores files on the local filesystem with an optional base path prefix.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, BinaryIO, Dict, List, Optional

from vorte.modules.storage.storage import StorageDriver


class LocalStorageDriver(StorageDriver):
    """Local filesystem storage driver."""

    def __init__(
        self,
        base_path: str = "storage/uploads",
        base_url: str = "/files",
        visibility: str = "public",
    ) -> None:
        self._base_path = Path(base_path).resolve()
        self._base_url = base_url.rstrip("/")
        self._visibility = visibility
        self._base_path.mkdir(parents=True, exist_ok=True)

    async def put(self, path: str, content: bytes, content_type: str = "", metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        full_path = self._base_path / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return {
            "path": path,
            "size": len(content),
            "content_type": content_type,
            "url": self.url(path),
        }

    async def get(self, path: str) -> bytes:
        full_path = self._base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return full_path.read_bytes()

    async def delete(self, path: str) -> None:
        full_path = self._base_path / path
        if full_path.exists():
            full_path.unlink()

    async def exists(self, path: str) -> bool:
        return (self._base_path / path).exists()

    async def url(self, path: str) -> str:
        return f"{self._base_url}/{path}"

    async def stream(self, path: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        full_path = self._base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        with open(full_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    async def copy(self, source: str, destination: str) -> None:
        src = self._base_path / source
        dst = self._base_path / destination
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    async def move(self, source: str, destination: str) -> None:
        src = self._base_path / source
        dst = self._base_path / destination
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    async def size(self, path: str) -> int:
        full_path = self._base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return full_path.stat().st_size

    async def last_modified(self, path: str) -> float:
        full_path = self._base_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return full_path.stat().st_mtime

    async def list_files(self, prefix: str = "") -> List[str]:
        base = self._base_path / prefix if prefix else self._base_path
        if not base.exists():
            return []
        paths = []
        for item in base.rglob("*"):
            if item.is_file():
                paths.append(str(item.relative_to(self._base_path)))
        return sorted(paths)

    async def cdn_url(self, path: str) -> str:
        """Local driver returns the base_url — configure a CDN in front of it."""
        return await self.url(path)

    async def ping(self) -> bool:
        return self._base_path.exists()
