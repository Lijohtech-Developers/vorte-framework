"""
Vorte Auth Models
=================
Database models for the authentication module: User, Role, Permission, APIKey.

These models are designed to work with SQLAlchemy but are also usable
independently for in-memory or custom storage backends.

Usage:
    from vorte.modules.auth.models import User, Role, Permission, APIKey
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class UserStatus(str, Enum):
    """User account status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"
    DELETED = "deleted"


class APIKeyStatus(str, Enum):
    """API key status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    REVOKED = "revoked"


@dataclass
class Permission:
    """
    Represents a granular permission in the RBAC system.

    Permissions follow a dot-notation convention: ``resource.action``
    (e.g. ``posts.create``, ``users.delete``).

    Attributes:
        name: Unique permission identifier (e.g. 'posts.create').
        description: Human-readable description.
        resource: The resource this permission applies to (e.g. 'posts').
        action: The action allowed (e.g. 'create', 'read', 'update', 'delete').
    """
    name: str
    description: str = ""
    resource: str = ""
    action: str = ""

    def __post_init__(self) -> None:
        """Extract resource and action from name if not explicitly set."""
        if not self.resource or not self.action:
            parts = self.name.split(".", 1)
            if len(parts) == 2:
                if not self.resource:
                    self.resource = parts[0]
                if not self.action:
                    self.action = parts[1]

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Permission):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return NotImplemented


@dataclass
class Role:
    """
    Represents a role that bundles multiple permissions.

    Roles are assigned to users. Each role can have zero or more permissions.

    Attributes:
        name: Unique role name (e.g. 'admin', 'editor', 'viewer').
        description: Human-readable description.
        permissions: Set of Permission instances granted by this role.
        is_default: Whether this role is assigned to new users by default.
        priority: Role priority level (higher = more authoritative).
    """
    name: str
    description: str = ""
    permissions: Set[Permission] = field(default_factory=set)
    is_default: bool = False
    priority: int = 0

    def has_permission(self, permission: str) -> bool:
        """Check if the role has a specific permission by name."""
        return any(
            p.name == permission
            or (p.resource == "*" and p.action == "*")
            or (p.resource == permission.split(".", 1)[0] and p.action == "*")
            for p in self.permissions
        )

    def add_permission(self, permission: Permission) -> None:
        """Add a permission to this role."""
        self.permissions.add(permission)

    def remove_permission(self, permission_name: str) -> None:
        """Remove a permission from this role by name."""
        self.permissions = {p for p in self.permissions if p.name != permission_name}

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Role):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return NotImplemented


@dataclass
class User:
    """
    Represents an authenticated user in the system.

    Attributes:
        id: Unique user identifier (UUID).
        email: User's email address (unique).
        username: User's display name / handle.
        hashed_password: Bcrypt-hashed password string.
        status: Current account status.
        roles: Set of Role instances assigned to the user.
        mfa_enabled: Whether multi-factor authentication is enabled.
        mfa_secret: TOTP secret key (encrypted at rest in production).
        email_verified: Whether the user has verified their email.
        avatar_url: Optional profile picture URL.
        metadata: Arbitrary key-value metadata attached to the user.
        tier: Subscription tier (e.g. 'free', 'pro', 'enterprise').
        last_login_at: Timestamp of the most recent login.
        created_at: Timestamp of account creation.
        updated_at: Timestamp of last profile update.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    email: str = ""
    username: str = ""
    hashed_password: str = ""
    status: UserStatus = UserStatus.ACTIVE
    roles: Set[Role] = field(default_factory=set)
    mfa_enabled: bool = False
    mfa_secret: str = ""
    email_verified: bool = False
    avatar_url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    tier: str = "free"
    last_login_at: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # --- Role / Permission Helpers ---

    def add_role(self, role: Role) -> None:
        """Assign a role to this user."""
        self.roles.add(role)

    def remove_role(self, role_name: str) -> None:
        """Remove a role from this user by name."""
        self.roles = {r for r in self.roles if r.name != role_name}

    def has_role(self, role_name: str) -> bool:
        """Check if the user has a specific role."""
        return any(r.name == role_name for r in self.roles)

    def get_all_permissions(self) -> Set[Permission]:
        """Aggregate all permissions from all assigned roles."""
        permissions: Set[Permission] = set()
        for role in self.roles:
            permissions.update(role.permissions)
        return permissions

    def has_permission(self, permission_name: str) -> bool:
        """Check if the user has a specific permission through any role."""
        return any(role.has_permission(permission_name) for role in self.roles)

    def is_admin(self) -> bool:
        """Check if the user has an admin role."""
        return self.has_role("admin") or self.has_role("superadmin")

    def is_active(self) -> bool:
        """Check if the user account is active."""
        return self.status == UserStatus.ACTIVE

    def within_tier(self, required_tier: str) -> bool:
        """
        Check if the user's subscription tier meets or exceeds a requirement.

        Tiers (lowest to highest): ``free``, ``pro``, ``enterprise``.
        """
        tier_hierarchy = {"free": 0, "starter": 1, "pro": 2, "enterprise": 3}
        user_level = tier_hierarchy.get(self.tier, 0)
        required_level = tier_hierarchy.get(required_tier, 0)
        return user_level >= required_level

    # --- Serialization ---

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the user to a dictionary (excludes sensitive fields)."""
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "status": self.status.value,
            "roles": [r.name for r in self.roles],
            "permissions": [p.name for p in self.get_all_permissions()],
            "mfa_enabled": self.mfa_enabled,
            "email_verified": self.email_verified,
            "avatar_url": self.avatar_url,
            "tier": self.tier,
            "last_login_at": self.last_login_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class APIKey:
    """
    Represents an API key for programmatic authentication.

    API keys allow machine-to-machine authentication without requiring
    a user to log in interactively. Keys are prefixed with ``vorte_``.

    Attributes:
        id: Unique identifier for the API key.
        name: Human-readable label for the key.
        key_hash: SHA-256 hash of the raw key (the raw key is shown only once).
        key_prefix: First 8 characters of the key for identification.
        user_id: ID of the user who owns this key.
        scopes: List of permission scopes granted by this key.
        status: Current key status.
        expires_at: Optional expiration timestamp.
        last_used_at: Timestamp of last successful use.
        rate_limit: Maximum requests per minute (0 = unlimited).
        created_at: Key creation timestamp.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    key_hash: str = ""
    key_prefix: str = ""
    user_id: str = ""
    scopes: List[str] = field(default_factory=list)
    status: APIKeyStatus = APIKeyStatus.ACTIVE
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    rate_limit: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def generate(cls, name: str, user_id: str, scopes: Optional[List[str]] = None,
                 expires_at: Optional[str] = None, rate_limit: int = 0) -> tuple["APIKey", str]:
        """
        Generate a new API key.

        Returns a tuple of (APIKey instance, raw_key).
        The raw key is returned only once and should be shown to the user.

        Args:
            name: Human-readable label.
            user_id: Owner's user ID.
            scopes: Permission scopes (defaults to ['read']).
            expires_at: Optional ISO expiration timestamp.
            rate_limit: Max requests per minute (0 = unlimited).

        Returns:
            Tuple of (APIKey, raw_key_string).
        """
        raw_key = f"vorte_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:12]

        instance = cls(
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            user_id=user_id,
            scopes=scopes or ["read"],
            expires_at=expires_at,
            rate_limit=rate_limit,
        )
        return instance, raw_key

    def verify_key(self, raw_key: str) -> bool:
        """Verify a raw key against the stored hash."""
        computed = hashlib.sha256(raw_key.encode()).hexdigest()
        return secrets.compare_digest(computed, self.key_hash)

    def is_expired(self) -> bool:
        """Check if the API key has expired."""
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > expires
        except (ValueError, TypeError):
            return False

    def is_valid(self) -> bool:
        """Check if the API key is active and not expired."""
        return (
            self.status == APIKeyStatus.ACTIVE
            and not self.is_expired()
        )

    def has_scope(self, scope: str) -> bool:
        """Check if the key grants a specific scope."""
        return scope in self.scopes or "*" in self.scopes

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the API key (excludes the key hash)."""
        return {
            "id": self.id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "user_id": self.user_id,
            "scopes": self.scopes,
            "status": self.status.value,
            "expires_at": self.expires_at,
            "last_used_at": self.last_used_at,
            "rate_limit": self.rate_limit,
            "created_at": self.created_at,
        }
