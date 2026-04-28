"""
Vorte API Key Manager
======================
Manages the lifecycle of API keys: creation, validation, rotation,
revocation, and lookup.

In-memory store is used by default. A persistent backend (database, Redis)
can be provided via the ``storage`` parameter.

Usage:
    manager = APIKeyManager()

    # Create a key
    api_key, raw_key = await manager.create_key(
        name="CI Pipeline",
        user_id="usr_abc",
        scopes=["read", "write"],
    )

    # Validate a key from a request header
    key_info = await manager.validate_key(raw_key)
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from vorte.modules.auth.models import APIKey, APIKeyStatus
from vorte.modules.auth.jwt import APIKeyInvalidError


class APIKeyStorage:
    """
    Abstract storage interface for API keys.

    Subclass this to provide a persistent backend (database, Redis, etc.).
    """

    async def save(self, key: APIKey) -> None:
        """Persist an API key."""
        raise NotImplementedError

    async def find_by_hash(self, key_hash: str) -> Optional[APIKey]:
        """Look up an API key by its SHA-256 hash."""
        raise NotImplementedError

    async def find_by_id(self, key_id: str) -> Optional[APIKey]:
        """Look up an API key by its ID."""
        raise NotImplementedError

    async def find_by_user(self, user_id: str) -> List[APIKey]:
        """List all API keys belonging to a user."""
        raise NotImplementedError

    async def delete(self, key_id: str) -> bool:
        """Delete an API key by ID."""
        raise NotImplementedError

    async def update(self, key: APIKey) -> None:
        """Update an existing API key."""
        raise NotImplementedError


class InMemoryAPIKeyStorage(APIKeyStorage):
    """In-memory implementation of APIKeyStorage for development and testing."""

    def __init__(self) -> None:
        self._keys: Dict[str, APIKey] = {}  # keyed by id
        self._hash_index: Dict[str, str] = {}  # key_hash -> key_id

    async def save(self, key: APIKey) -> None:
        self._keys[key.id] = key
        self._hash_index[key.key_hash] = key.id

    async def find_by_hash(self, key_hash: str) -> Optional[APIKey]:
        key_id = self._hash_index.get(key_hash)
        if key_id:
            return self._keys.get(key_id)
        return None

    async def find_by_id(self, key_id: str) -> Optional[APIKey]:
        return self._keys.get(key_id)

    async def find_by_user(self, user_id: str) -> List[APIKey]:
        return [k for k in self._keys.values() if k.user_id == user_id]

    async def delete(self, key_id: str) -> bool:
        key = self._keys.pop(key_id, None)
        if key:
            self._hash_index.pop(key.key_hash, None)
            return True
        return False

    async def update(self, key: APIKey) -> None:
        self._keys[key.id] = key
        self._hash_index[key.key_hash] = key.id


class APIKeyManager:
    """
    Manages API key lifecycle.

    Args:
        storage: Storage backend (defaults to InMemoryAPIKeyStorage).
        default_scopes: Default scopes for new keys.
        default_expires_in_days: Default expiry in days (None = never).
        max_keys_per_user: Maximum number of active keys per user (0 = unlimited).
    """

    def __init__(
        self,
        storage: Optional[APIKeyStorage] = None,
        default_scopes: Optional[List[str]] = None,
        default_expires_in_days: Optional[int] = None,
        max_keys_per_user: int = 0,
    ):
        self._storage = storage or InMemoryAPIKeyStorage()
        self._default_scopes = default_scopes or ["read"]
        self._default_expires_in_days = default_expires_in_days
        self._max_keys_per_user = max_keys_per_user

    # ------------------------------------------------------------------
    # Key Creation
    # ------------------------------------------------------------------

    async def create_key(
        self,
        name: str,
        user_id: str,
        scopes: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
        rate_limit: int = 0,
    ) -> tuple[APIKey, str]:
        """
        Generate and store a new API key.

        Args:
            name: Human-readable label.
            user_id: ID of the owning user.
            scopes: Permission scopes (defaults to manager defaults).
            expires_in_days: Days until expiry (None = never expire).
            rate_limit: Max requests per minute (0 = unlimited).

        Returns:
            Tuple of (APIKey instance, raw_key_string).
            The raw key is returned only once.

        Raises:
            ValueError: If max_keys_per_user limit is exceeded.
        """
        # Enforce per-user key limit
        if self._max_keys_per_user > 0:
            existing = await self._storage.find_by_user(user_id)
            active_count = sum(1 for k in existing if k.status == APIKeyStatus.ACTIVE)
            if active_count >= self._max_keys_per_user:
                raise ValueError(
                    f"User '{user_id}' has reached the maximum of "
                    f"{self._max_keys_per_user} active API keys"
                )

        # Determine expiration
        expires_at: Optional[str] = None
        days = expires_in_days if expires_in_days is not None else self._default_expires_in_days
        if days is not None:
            expires_dt = datetime.now(timezone.utc) + timedelta(days=days)
            expires_at = expires_dt.isoformat()

        api_key, raw_key = APIKey.generate(
            name=name,
            user_id=user_id,
            scopes=scopes or self._default_scopes,
            expires_at=expires_at,
            rate_limit=rate_limit,
        )

        await self._storage.save(api_key)
        return api_key, raw_key

    # ------------------------------------------------------------------
    # Key Validation
    # ------------------------------------------------------------------

    async def validate_key(self, raw_key: str) -> APIKey:
        """
        Validate a raw API key and return the stored key record.

        Args:
            raw_key: The raw API key from the request header.

        Returns:
            The APIKey instance if valid.

        Raises:
            APIKeyInvalidError: If the key is invalid, expired, or revoked.
        """
        if not raw_key:
            raise APIKeyInvalidError("API key is required")

        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        api_key = await self._storage.find_by_hash(key_hash)

        if not api_key:
            raise APIKeyInvalidError("Invalid API key")

        if not api_key.is_valid():
            if api_key.is_expired():
                raise APIKeyInvalidError("API key has expired")
            raise APIKeyInvalidError("API key has been revoked or is inactive")

        # Update last_used_at
        api_key.last_used_at = datetime.now(timezone.utc).isoformat()
        await self._storage.update(api_key)

        return api_key

    async def validate_key_with_scope(self, raw_key: str, scope: str) -> APIKey:
        """
        Validate an API key and check that it has a specific scope.

        Args:
            raw_key: The raw API key.
            scope: Required scope.

        Returns:
            The APIKey instance.

        Raises:
            APIKeyInvalidError: If the key is invalid or lacks the scope.
        """
        api_key = await self.validate_key(raw_key)
        if not api_key.has_scope(scope):
            raise APIKeyInvalidError(
                f"API key lacks required scope '{scope}'"
            )
        return api_key

    # ------------------------------------------------------------------
    # Key Lookup
    # ------------------------------------------------------------------

    async def get_key(self, key_id: str) -> Optional[APIKey]:
        """Retrieve a key by ID (without the raw key)."""
        return await self._storage.find_by_id(key_id)

    async def list_user_keys(self, user_id: str) -> List[APIKey]:
        """List all keys belonging to a user."""
        return await self._storage.find_by_user(user_id)

    # ------------------------------------------------------------------
    # Key Management
    # ------------------------------------------------------------------

    async def revoke_key(self, key_id: str) -> bool:
        """
        Revoke an API key by setting its status to REVOKED.

        Args:
            key_id: The API key ID.

        Returns:
            True if the key was found and revoked.
        """
        api_key = await self._storage.find_by_id(key_id)
        if api_key:
            api_key.status = APIKeyStatus.REVOKED
            await self._storage.update(api_key)
            return True
        return False

    async def delete_key(self, key_id: str) -> bool:
        """
        Permanently delete an API key.

        Args:
            key_id: The API key ID.

        Returns:
            True if the key was found and deleted.
        """
        return await self._storage.delete(key_id)

    async def rotate_key(self, key_id: str) -> tuple[APIKey, str]:
        """
        Rotate an API key: revoke the old key and create a new one with
        the same configuration.

        Args:
            key_id: The API key ID to rotate.

        Returns:
            Tuple of (new APIKey instance, new raw_key_string).

        Raises:
            APIKeyInvalidError: If the original key is not found.
        """
        old_key = await self._storage.find_by_id(key_id)
        if not old_key:
            raise APIKeyInvalidError("API key not found")

        # Revoke the old key
        old_key.status = APIKeyStatus.REVOKED
        await self._storage.update(old_key)

        # Calculate remaining days if the old key has an expiry
        expires_in_days: Optional[int] = None
        if old_key.expires_at:
            try:
                expires_dt = datetime.fromisoformat(old_key.expires_at)
                remaining = (expires_dt - datetime.now(timezone.utc)).days
                if remaining > 0:
                    expires_in_days = remaining
            except (ValueError, TypeError):
                pass

        # Create a replacement key
        new_key, raw_key = await self.create_key(
            name=old_key.name,
            user_id=old_key.user_id,
            scopes=list(old_key.scopes),
            expires_in_days=expires_in_days,
            rate_limit=old_key.rate_limit,
        )
        return new_key, raw_key
