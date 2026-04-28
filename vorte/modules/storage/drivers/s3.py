"""
Vorte Storage Module — S3-Compatible Driver
============================================
Works with Amazon S3, MinIO, DigitalOcean Spaces, and any S3-compatible service.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from vorte.modules.storage.storage import StorageDriver

logger = logging.getLogger("vorte.modules.storage.s3")


class S3StorageDriver(StorageDriver):
    """Amazon S3 / S3-compatible storage driver."""

    def __init__(
        self,
        bucket: str = "",
        access_key: str = "",
        secret_key: str = "",
        region: str = "us-east-1",
        endpoint_url: str = "",
        cdn_url: str = "",
        acl: str = "private",
    ) -> None:
        self._bucket = bucket
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._endpoint_url = endpoint_url
        self._cdn_url = cdn_url.rstrip("/") if cdn_url else ""
        self._acl = acl
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config as BotoConfig
            kwargs: Dict[str, Any] = {
                "aws_access_key_id": self._access_key,
                "aws_secret_access_key": self._secret_key,
                "region_name": self._region,
                "config": BotoConfig(retries={"max_attempts": 3}),
            }
            if self._endpoint_url:
                kwargs["endpoint_url"] = self._endpoint_url
            self._client = boto3.client("s3", **kwargs)
        except ImportError:
            raise RuntimeError("boto3 package is required.  pip install boto3")
        return self._client

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a blocking boto3 call in a thread."""
        return await asyncio.to_thread(func, *args, **kwargs)

    async def put(self, path: str, content: bytes, content_type: str = "", metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        client = self._get_client()
        extra: Dict[str, Any] = {"ACL": self._acl}
        if content_type:
            extra["ContentType"] = content_type
        if metadata:
            extra["Metadata"] = metadata
        await self._run(client.put_object, Bucket=self._bucket, Key=path, Body=content, **extra)
        return {
            "path": path,
            "size": len(content),
            "content_type": content_type,
            "url": self.url(path),
        }

    async def get(self, path: str) -> bytes:
        client = self._get_client()
        resp = await self._run(client.get_object, Bucket=self._bucket, Key=path)
        return resp["Body"].read()

    async def delete(self, path: str) -> None:
        client = self._get_client()
        await self._run(client.delete_object, Bucket=self._bucket, Key=path)

    async def exists(self, path: str) -> bool:
        client = self._get_client()
        try:
            await self._run(client.head_object, Bucket=self._bucket, Key=path)
            return True
        except Exception:
            return False

    async def url(self, path: str) -> str:
        if self._cdn_url:
            return f"{self._cdn_url}/{path}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{path}"

    async def presigned_url(self, path: str, expires_in: int = 3600) -> str:
        client = self._get_client()
        return await self._run(
            client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": path},
            ExpiresIn=expires_in,
        )

    async def stream(self, path: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        data = await self.get(path)
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    async def copy(self, source: str, destination: str) -> None:
        client = self._get_client()
        await self._run(
            client.copy_object,
            Bucket=self._bucket,
            Key=destination,
            CopySource={"Bucket": self._bucket, "Key": source},
        )

    async def move(self, source: str, destination: str) -> None:
        await self.copy(source, destination)
        await self.delete(source)

    async def size(self, path: str) -> int:
        client = self._get_client()
        resp = await self._run(client.head_object, Bucket=self._bucket, Key=path)
        return resp.get("ContentLength", 0)

    async def last_modified(self, path: str) -> float:
        client = self._get_client()
        resp = await self._run(client.head_object, Bucket=self._bucket, Key=path)
        from datetime import datetime, timezone
        lm = resp.get("LastModified")
        if lm:
            return lm.replace(tzinfo=timezone.utc).timestamp()
        return 0.0

    async def list_files(self, prefix: str = "") -> List[str]:
        client = self._get_client()
        resp = await self._run(client.list_objects_v2, Bucket=self._bucket, Prefix=prefix)
        return [obj["Key"] for obj in resp.get("Contents", [])]

    async def cdn_url(self, path: str) -> str:
        if self._cdn_url:
            return f"{self._cdn_url}/{path}"
        return await self.url(path)

    async def ping(self) -> bool:
        try:
            client = self._get_client()
            await self._run(client.head_bucket, Bucket=self._bucket)
            return True
        except Exception:
            return False
