"""
Vorte Session Manager
======================
Server-side session management supporting cookie-based or token-based
sessions. Tracks active sessions per user, supports forced logout,
and can operate with an in-memory store or a Redis backend.

Usage:
    manager = SessionManager()

    # Create a session
    session = await manager.create_session(user_id="usr_abc", request=request)

    # Validate a session from a cookie/token
    session = await manager.validate_session("sess_abc123")

    # Destroy a session (logout)
    await manager.destroy_session("sess_abc123")
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from vorte.modules.auth.jwt import SessionInvalidError


@dataclass
class Session:
    """
    Represents an active user session.

    Attributes:
        session_id: Unique session identifier.
        user_id: ID of the authenticated user.
        ip_address: Client IP address.
        user_agent: Client User-Agent header.
        created_at: Session creation timestamp.
        last_activity: Timestamp of last request / activity.
        expires_at: Session expiration timestamp.
        data: Arbitrary session data (flash messages, etc.).
        is_current: Whether this is the session making the current request.
    """
    session_id: str
    user_id: str
    ip_address: str = ""
    user_agent: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_activity: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    expires_at: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    is_current: bool = False

    def is_expired(self) -> bool:
        """Check if the session has expired."""
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > expires
        except (ValueError, TypeError):
            return False

    def touch(self) -> None:
        """Update last_activity to the current time."""
        self.last_activity = datetime.now(timezone.utc).isoformat()

    def set(self, key: str, value: Any) -> None:
        """Store a key-value pair in session data."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from session data."""
        return self.data.get(key, default)

    def delete(self, key: str) -> None:
        """Remove a key from session data."""
        self.data.pop(key, None)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the session to a dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "expires_at": self.expires_at,
            "is_current": self.is_current,
        }


class SessionStorage:
    """Abstract storage interface for sessions."""

    async def save(self, session: Session) -> None:
        raise NotImplementedError

    async def find(self, session_id: str) -> Optional[Session]:
        raise NotImplementedError

    async def find_by_user(self, user_id: str) -> List[Session]:
        raise NotImplementedError

    async def delete(self, session_id: str) -> bool:
        raise NotImplementedError

    async def delete_by_user(self, user_id: str) -> int:
        """Delete all sessions for a user. Returns the count deleted."""
        raise NotImplementedError


class InMemorySessionStorage(SessionStorage):
    """In-memory session storage for development and testing."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._user_index: Dict[str, List[str]] = {}

    async def save(self, session: Session) -> None:
        self._sessions[session.session_id] = session
        if session.user_id not in self._user_index:
            self._user_index[session.user_id] = []
        if session.session_id not in self._user_index[session.user_id]:
            self._user_index[session.user_id].append(session.session_id)

    async def find(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    async def find_by_user(self, user_id: str) -> List[Session]:
        session_ids = self._user_index.get(user_id, [])
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]

    async def delete(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session:
            ids = self._user_index.get(session.user_id, [])
            if session_id in ids:
                ids.remove(session_id)
            return True
        return False

    async def delete_by_user(self, user_id: str) -> int:
        session_ids = self._user_index.pop(user_id, [])
        count = 0
        for sid in session_ids:
            if self._sessions.pop(sid, None) is not None:
                count += 1
        return count


class SessionManager:
    """
    Manages user sessions with configurable storage backend.

    Args:
        storage: Session storage backend (defaults to InMemorySessionStorage).
        session_ttl_seconds: Session lifetime in seconds (default 24 hours).
        max_sessions_per_user: Max concurrent sessions per user (0 = unlimited).
    """

    def __init__(
        self,
        storage: Optional[SessionStorage] = None,
        session_ttl_seconds: int = 86400,
        max_sessions_per_user: int = 0,
    ):
        self._storage = storage or InMemorySessionStorage()
        self._session_ttl = session_ttl_seconds
        self._max_sessions_per_user = max_sessions_per_user

    # ------------------------------------------------------------------
    # Session Lifecycle
    # ------------------------------------------------------------------

    async def create_session(
        self,
        user_id: str,
        ip_address: str = "",
        user_agent: str = "",
        ttl_override: Optional[int] = None,
    ) -> Session:
        """
        Create a new session for a user.

        Args:
            user_id: ID of the authenticated user.
            ip_address: Client IP address.
            user_agent: Client User-Agent.
            ttl_override: Custom TTL in seconds (overrides default).

        Returns:
            The created Session instance.
        """
        # Enforce per-user session limit
        if self._max_sessions_per_user > 0:
            existing = await self._storage.find_by_user(user_id)
            if len(existing) >= self._max_sessions_per_user:
                # Evict the oldest session
                oldest = min(existing, key=lambda s: s.created_at)
                await self._storage.delete(oldest.session_id)

        ttl = ttl_override or self._session_ttl
        expires_dt = datetime.now(timezone.utc).__class__(
            datetime.now(timezone.utc).year,
            datetime.now(timezone.utc).month,
            datetime.now(timezone.utc).day,
            datetime.now(timezone.utc).hour,
            datetime.now(timezone.utc).minute,
            datetime.now(timezone.utc).second,
            tzinfo=timezone.utc,
        )
        import datetime as _dt
        now = _dt.datetime.now(timezone.utc)
        expires_at = (now + _dt.timedelta(seconds=ttl)).isoformat()

        session = Session(
            session_id=f"sess_{secrets.token_urlsafe(24)}",
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )

        await self._storage.save(session)
        return session

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_session(self, session_id: str) -> Session:
        """
        Validate a session ID and return the session.

        Touches the session to update last_activity.

        Args:
            session_id: The session ID to validate.

        Returns:
            The Session instance.

        Raises:
            SessionInvalidError: If the session is invalid or expired.
        """
        if not session_id:
            raise SessionInvalidError("Session ID is required")

        session = await self._storage.find(session_id)
        if not session:
            raise SessionInvalidError("Session not found")

        if session.is_expired():
            await self._storage.delete(session_id)
            raise SessionInvalidError("Session has expired")

        session.touch()
        await self._storage.save(session)
        return session

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve a session without validation (does not touch)."""
        return await self._storage.find(session_id)

    async def list_user_sessions(
        self, user_id: str, current_session_id: Optional[str] = None
    ) -> List[Session]:
        """
        List all active sessions for a user.

        Args:
            user_id: User ID to list sessions for.
            current_session_id: Mark the current session (if provided).

        Returns:
            List of Session instances (excluding expired ones).
        """
        sessions = await self._storage.find_by_user(user_id)
        active = [s for s in sessions if not s.is_expired()]

        if current_session_id:
            for s in active:
                s.is_current = s.session_id == current_session_id

        return active

    # ------------------------------------------------------------------
    # Destruction
    # ------------------------------------------------------------------

    async def destroy_session(self, session_id: str) -> bool:
        """
        Destroy a specific session (logout).

        Args:
            session_id: Session ID to destroy.

        Returns:
            True if the session was found and destroyed.
        """
        return await self._storage.delete(session_id)

    async def destroy_all_user_sessions(self, user_id: str) -> int:
        """
        Destroy all sessions for a user (force logout everywhere).

        Args:
            user_id: User ID.

        Returns:
            Number of sessions destroyed.
        """
        return await self._storage.delete_by_user(user_id)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def cleanup_expired(self) -> int:
        """
        Remove all expired sessions from storage.

        Returns:
            Number of sessions removed.
        """
        # Default implementation iterates all sessions.
        # Production implementations should use TTL-based expiry in Redis.
        if hasattr(self._storage, "_sessions"):
            storage = self._storage  # type: InMemorySessionStorage
            expired_ids = [
                sid for sid, session in storage._sessions.items()
                if session.is_expired()
            ]
            for sid in expired_ids:
                await storage.delete(sid)
            return len(expired_ids)
        return 0
