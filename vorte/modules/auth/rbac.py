"""
Vorte RBAC Manager
==================
Role-Based Access Control manager. Provides an in-memory registry for
roles and permissions, with methods for creating, querying, and enforcing
access policies.

Usage:
    rbac = RBACManager()

    # Bootstrap default roles
    rbac.bootstrap_default_roles()

    # Check permissions
    allowed = rbac.user_has_permission(user, "posts.create")
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Set, TYPE_CHECKING

from vorte.modules.auth.models import Permission, Role
from vorte.modules.auth.jwt import PermissionDeniedError

if TYPE_CHECKING:
    from vorte.modules.auth.models import User


class RBACManager:
    """
    Manages roles and permissions for the RBAC system.

    Stores role definitions in memory and provides lookup / enforcement
    methods. In production, role assignments are persisted via the User model
    and a database layer.

    Attributes:
        roles: Dictionary of role_name -> Role instance.
        permissions: Dictionary of permission_name -> Permission instance.
    """

    def __init__(self) -> None:
        self._roles: Dict[str, Role] = {}
        self._permissions: Dict[str, Permission] = {}
        self._superadmin_permissions: Set[str] = {"*"}

    # ------------------------------------------------------------------
    # Role Management
    # ------------------------------------------------------------------

    def create_role(
        self,
        name: str,
        description: str = "",
        permissions: Optional[List[str]] = None,
        is_default: bool = False,
        priority: int = 0,
    ) -> Role:
        """
        Create and register a new role.

        Args:
            name: Unique role name (lowercase, alphanumeric + _-).
            description: Human-readable description.
            permissions: List of permission names to assign.
            is_default: Whether this is assigned to new users.
            priority: Role priority (higher = more authoritative).

        Returns:
            The created Role instance.

        Raises:
            ValueError: If a role with the same name already exists.
        """
        if name in self._roles:
            raise ValueError(f"Role '{name}' already exists")

        role = Role(
            name=name,
            description=description,
            is_default=is_default,
            priority=priority,
        )

        for perm_name in (permissions or []):
            perm = self._permissions.get(perm_name)
            if perm:
                role.add_permission(perm)
            else:
                # Auto-create permission if it doesn't exist
                perm = self.create_permission(perm_name)
                role.add_permission(perm)

        self._roles[name] = role
        return role

    def get_role(self, name: str) -> Optional[Role]:
        """Retrieve a role by name. Returns None if not found."""
        return self._roles.get(name)

    def get_all_roles(self) -> Dict[str, Role]:
        """Return all registered roles."""
        return dict(self._roles)

    def update_role(
        self,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
        is_default: Optional[bool] = None,
        priority: Optional[int] = None,
    ) -> Role:
        """
        Update an existing role.

        Args:
            name: Role name to update.
            description: New description (or None to keep existing).
            permissions: New permission list (replaces all, or None to keep).
            is_default: New default flag (or None to keep).
            priority: New priority (or None to keep).

        Returns:
            The updated Role instance.

        Raises:
            ValueError: If the role does not exist.
        """
        role = self._roles.get(name)
        if not role:
            raise ValueError(f"Role '{name}' not found")

        if description is not None:
            role.description = description
        if permissions is not None:
            role.permissions = set()
            for perm_name in permissions:
                perm = self._permissions.get(perm_name)
                if perm:
                    role.add_permission(perm)
                else:
                    perm = self.create_permission(perm_name)
                    role.add_permission(perm)
        if is_default is not None:
            role.is_default = is_default
        if priority is not None:
            role.priority = priority

        return role

    def delete_role(self, name: str) -> bool:
        """
        Delete a role by name.

        Args:
            name: Role name to delete.

        Returns:
            True if the role was found and removed, False otherwise.
        """
        if name in self._roles:
            del self._roles[name]
            return True
        return False

    def get_default_role(self) -> Optional[Role]:
        """Return the default role assigned to new users."""
        for role in self._roles.values():
            if role.is_default:
                return role
        return None

    # ------------------------------------------------------------------
    # Permission Management
    # ------------------------------------------------------------------

    def create_permission(self, name: str, description: str = "") -> Permission:
        """
        Create and register a new permission.

        Args:
            name: Unique permission name in dot-notation (e.g. ``posts.create``).
            description: Human-readable description.

        Returns:
            The created Permission instance.

        Raises:
            ValueError: If a permission with the same name already exists.
        """
        if name in self._permissions:
            return self._permissions[name]

        permission = Permission(name=name, description=description)
        self._permissions[name] = permission
        return permission

    def get_permission(self, name: str) -> Optional[Permission]:
        """Retrieve a permission by name. Returns None if not found."""
        return self._permissions.get(name)

    def get_all_permissions(self) -> Dict[str, Permission]:
        """Return all registered permissions."""
        return dict(self._permissions)

    def delete_permission(self, name: str) -> bool:
        """
        Delete a permission by name.

        Also removes it from all roles.

        Args:
            name: Permission name to delete.

        Returns:
            True if found and removed, False otherwise.
        """
        if name not in self._permissions:
            return False

        del self._permissions[name]
        for role in self._roles.values():
            role.remove_permission(name)
        return True

    # ------------------------------------------------------------------
    # Access Checking
    # ------------------------------------------------------------------

    def user_has_role(self, user: "User", role_name: str) -> bool:
        """Check if a user has a specific role."""
        return user.has_role(role_name)

    def user_has_permission(self, user: "User", permission_name: str) -> bool:
        """
        Check if a user has a specific permission through any of their roles.

        Superadmin users are granted all permissions.

        Args:
            user: The User instance.
            permission_name: Permission to check (e.g. ``posts.create``).

        Returns:
            True if the user has the permission.
        """
        if user.is_admin():
            return True

        # Check wildcard permission on user
        if "*" in [p.name for p in user.get_all_permissions()]:
            return True

        return user.has_permission(permission_name)

    def user_has_any_permission(self, user: "User", *permission_names: str) -> bool:
        """Check if a user has at least one of the given permissions."""
        if user.is_admin():
            return True
        return any(self.user_has_permission(user, p) for p in permission_names)

    def user_has_all_permissions(self, user: "User", *permission_names: str) -> bool:
        """Check if a user has all of the given permissions."""
        if user.is_admin():
            return True
        return all(self.user_has_permission(user, p) for p in permission_names)

    def enforce_permission(self, user: "User", permission_name: str) -> None:
        """
        Enforce a permission check. Raises PermissionDeniedError if not granted.

        Args:
            user: The User instance.
            permission_name: Required permission.

        Raises:
            PermissionDeniedError: If the user lacks the permission.
        """
        if not self.user_has_permission(user, permission_name):
            raise PermissionDeniedError(
                f"User '{user.id}' lacks permission '{permission_name}'"
            )

    def enforce_role(self, user: "User", role_name: str) -> None:
        """
        Enforce a role check. Raises PermissionDeniedError if not assigned.

        Args:
            user: The User instance.
            role_name: Required role.

        Raises:
            PermissionDeniedError: If the user lacks the role.
        """
        if not self.user_has_role(user, role_name):
            raise PermissionDeniedError(
                f"User '{user.id}' lacks role '{role_name}'"
            )

    def enforce_tier(self, user: "User", required_tier: str) -> None:
        """
        Enforce a subscription tier check.

        Args:
            user: The User instance.
            required_tier: Required tier name.

        Raises:
            PermissionDeniedError: If the user's tier is below the requirement.
        """
        if not user.within_tier(required_tier):
            raise PermissionDeniedError(
                f"Requires '{required_tier}' tier or higher (current: '{user.tier}')"
            )

    # ------------------------------------------------------------------
    # Bootstrap Defaults
    # ------------------------------------------------------------------

    def bootstrap_default_roles(self) -> Dict[str, Role]:
        """
        Create sensible default roles and permissions.

        Creates:
        - **superadmin**: Full access to everything.
        - **admin**: Full access to most resources.
        - **editor**: Create, read, update content.
        - **viewer**: Read-only access.
        - **user**: Basic authenticated user access.

        Returns:
            Dictionary of created roles.
        """
        # Default permissions
        default_perms = [
            # Users
            "users.read", "users.create", "users.update", "users.delete",
            # Posts/Content
            "posts.read", "posts.create", "posts.update", "posts.delete",
            # Roles & Permissions
            "roles.read", "roles.create", "roles.update", "roles.delete",
            # API Keys
            "api_keys.read", "api_keys.create", "api_keys.update", "api_keys.delete",
            # Settings
            "settings.read", "settings.update",
            # Audit
            "audit.read",
            # Webhooks
            "webhooks.read", "webhooks.create", "webhooks.update", "webhooks.delete",
        ]
        for perm_name in default_perms:
            self.create_permission(perm_name)

        # Wildcard permissions for superadmin
        self.create_permission("*", "Full access to all resources")

        # superadmin
        self.create_role(
            name="superadmin",
            description="Full system access with no restrictions",
            permissions=["*"],
            priority=100,
        )

        # admin
        self.create_role(
            name="admin",
            description="Administrative access to most resources",
            permissions=[
                "users.read", "users.create", "users.update", "users.delete",
                "posts.read", "posts.create", "posts.update", "posts.delete",
                "roles.read", "roles.update",
                "api_keys.read", "api_keys.create", "api_keys.update", "api_keys.delete",
                "settings.read", "settings.update",
                "audit.read",
                "webhooks.read", "webhooks.create", "webhooks.update", "webhooks.delete",
            ],
            priority=90,
        )

        # editor
        self.create_role(
            name="editor",
            description="Can create and edit content",
            permissions=[
                "users.read",
                "posts.read", "posts.create", "posts.update",
                "api_keys.read",
                "webhooks.read",
            ],
            priority=50,
        )

        # viewer
        self.create_role(
            name="viewer",
            description="Read-only access to most resources",
            permissions=[
                "users.read",
                "posts.read",
                "api_keys.read",
                "roles.read",
                "webhooks.read",
            ],
            priority=30,
        )

        # user (default)
        self.create_role(
            name="user",
            description="Basic authenticated user",
            permissions=[
                "users.read",
                "posts.read",
                "api_keys.read", "api_keys.create",
            ],
            is_default=True,
            priority=10,
        )

        return self._roles

    # ------------------------------------------------------------------
    # Async Wrappers
    # ------------------------------------------------------------------

    async def auser_has_permission(self, user: "User", permission_name: str) -> bool:
        """Async wrapper for user_has_permission."""
        return self.user_has_permission(user, permission_name)

    async def aenforce_permission(self, user: "User", permission_name: str) -> None:
        """Async wrapper for enforce_permission."""
        self.enforce_permission(user, permission_name)

    async def aenforce_role(self, user: "User", role_name: str) -> None:
        """Async wrapper for enforce_role."""
        self.enforce_role(user, role_name)

    async def aenforce_tier(self, user: "User", required_tier: str) -> None:
        """Async wrapper for enforce_tier."""
        self.enforce_tier(user, required_tier)
