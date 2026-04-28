"""
Vorte MFA Manager
==================
Multi-Factor Authentication using TOTP (Time-based One-Time Passwords).

Provides setup, verification, and disable flows. Uses ``pyotp`` for
TOTP generation/validation and ``qrcode`` for QR code URIs.

Usage:
    manager = MFAManager(issuer="MyApp")

    # Setup MFA for a user
    setup = manager.setup_mfa(user_id="usr_abc")
    # -> setup.secret, setup.qr_code_url, setup.backup_codes

    # Verify a TOTP code
    is_valid = manager.verify_code(setup.secret, "123456")

    # Disable MFA
    manager.disable_mfa(user_id="usr_abc", code="123456")
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from vorte.modules.auth.jwt import MFAInvalidCodeError


class MFAManager:
    """
    Manages TOTP-based Multi-Factor Authentication.

    Args:
        issuer: Issuer name shown in authenticator apps (e.g. "MyApp").
        digits: Number of digits in TOTP codes (default 6).
        interval: TOTP time step in seconds (default 30).
        backup_codes_count: Number of backup codes generated on setup.
        max_attempts: Maximum verification attempts before temporary lockout.
        lockout_duration_seconds: Duration of temporary lockout after max attempts.
    """

    def __init__(
        self,
        issuer: str = "VorteApp",
        digits: int = 6,
        interval: int = 30,
        backup_codes_count: int = 10,
        max_attempts: int = 5,
        lockout_duration_seconds: int = 300,
    ):
        self._issuer = issuer
        self._digits = digits
        self._interval = interval
        self._backup_codes_count = backup_codes_count
        self._max_attempts = max_attempts
        self._lockout_duration = lockout_duration_seconds

        # Pending setups: user_id -> secret (before MFA is confirmed)
        self._pending_secrets: Dict[str, str] = {}

        # Active secrets: user_id -> secret
        self._secrets: Dict[str, str] = {}

        # Backup codes: user_id -> set of hashed codes
        self._backup_codes: Dict[str, Set[str]] = {}

        # Failed attempt tracking: user_id -> {"count": int, "locked_until": str}
        self._attempt_tracker: Dict[str, Dict[str, int | str]] = {}

    # ------------------------------------------------------------------
    # TOTP Operations (require pyotp)
    # ------------------------------------------------------------------

    def _get_totp(self, secret: str):
        """Import and create a pyotp.TOTP instance."""
        import pyotp
        return pyotp.TOTP(secret, digits=self._digits, interval=self._interval)

    def _generate_secret(self) -> str:
        """Generate a new TOTP secret."""
        import pyotp
        return pyotp.random_base32()

    def _hash_backup_code(self, code: str) -> str:
        """Hash a backup code for safe storage."""
        return hashlib.sha256(code.encode()).hexdigest()

    def _generate_backup_codes(self) -> List[str]:
        """
        Generate random backup/recovery codes.

        Returns:
            List of plain-text codes (shown to the user once).
        """
        codes = []
        for _ in range(self._backup_codes_count):
            code = secrets.token_hex(4).upper()  # e.g. "A1B2C3D4"
            # Format as groups: "A1B2-C3D4"
            codes.append(f"{code[:4]}-{code[4:]}")
        return codes

    # ------------------------------------------------------------------
    # MFA Setup
    # ------------------------------------------------------------------

    def setup_mfa(
        self,
        user_id: str,
        email: str = "",
    ) -> Dict[str, object]:
        """
        Initiate MFA setup for a user.

        Generates a TOTP secret and backup codes. The user must verify
        one TOTP code before MFA is fully enabled.

        Args:
            user_id: The user's ID.
            email: User's email (used in the QR code issuer label).

        Returns:
            Dictionary with:
            - ``secret``: TOTP secret (for manual entry in auth apps).
            - ``qr_code_url``: ``otpauth://`` URI for QR code generation.
            - ``backup_codes``: List of plain-text recovery codes.
        """
        secret = self._generate_secret()
        self._pending_secrets[user_id] = secret

        # Generate QR code URL
        totp = self._get_totp(secret)
        label = email or user_id
        qr_code_url = totp.provisioning_uri(name=label, issuer_name=self._issuer)

        # Generate backup codes
        backup_codes = self._generate_backup_codes()
        hashed_codes = {self._hash_backup_code(c) for c in backup_codes}
        self._backup_codes[user_id] = hashed_codes

        return {
            "secret": secret,
            "qr_code_url": qr_code_url,
            "backup_codes": backup_codes,
        }

    def confirm_setup(self, user_id: str, code: str) -> bool:
        """
        Confirm MFA setup by verifying a TOTP code.

        If the code is valid, MFA is activated for the user.

        Args:
            user_id: The user's ID.
            code: 6-digit TOTP code from the authenticator app.

        Returns:
            True if MFA was successfully activated.

        Raises:
            MFAInvalidCodeError: If the code is invalid.
        """
        secret = self._pending_secrets.get(user_id)
        if not secret:
            raise MFAInvalidCodeError("No pending MFA setup for this user")

        if not self.verify_code(secret, code):
            raise MFAInvalidCodeError("Invalid TOTP code")

        # Promote from pending to active
        self._secrets[user_id] = secret
        del self._pending_secrets[user_id]
        return True

    # ------------------------------------------------------------------
    # Code Verification
    # ------------------------------------------------------------------

    def verify_code(self, secret: str, code: str) -> bool:
        """
        Verify a TOTP code against a secret.

        Args:
            secret: The TOTP secret.
            code: 6-digit code from the user's authenticator app.

        Returns:
            True if the code is valid.
        """
        try:
            totp = self._get_totp(secret)
            return totp.verify(code, valid_window=1)
        except Exception:
            return False

    async def verify_user_code(self, user_id: str, code: str) -> bool:
        """
        Verify a TOTP code for a user with rate limiting.

        Checks against the active secret (not pending). Implements
        temporary lockout after too many failed attempts.

        Args:
            user_id: The user's ID.
            code: 6-digit TOTP code.

        Returns:
            True if the code is valid.

        Raises:
            MFAInvalidCodeError: If locked out or code is invalid.
        """
        # Check lockout
        tracker = self._attempt_tracker.get(user_id)
        if tracker:
            count = tracker.get("count", 0)
            locked_until = tracker.get("locked_until")
            if locked_until and count >= self._max_attempts:
                lock_until = datetime.fromisoformat(str(locked_until))
                if datetime.now(timezone.utc) < lock_until:
                    raise MFAInvalidCodeError(
                        f"Too many failed attempts. Try again after "
                        f"{lock_until.strftime('%H:%M:%S')} UTC."
                    )
                # Lockout expired, reset
                self._attempt_tracker.pop(user_id, None)

        secret = self._secrets.get(user_id)
        if not secret:
            raise MFAInvalidCodeError("MFA is not enabled for this user")

        if self.verify_code(secret, code):
            # Reset attempts on success
            self._attempt_tracker.pop(user_id, None)
            return True

        # Increment failed attempts
        if user_id not in self._attempt_tracker:
            self._attempt_tracker[user_id] = {"count": 0, "locked_until": ""}
        self._attempt_tracker[user_id]["count"] = (
            self._attempt_tracker[user_id]["count"] + 1
        )

        count = self._attempt_tracker[user_id]["count"]
        if count >= self._max_attempts:
            lock_until = datetime.now(timezone.utc).__class__(
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
            lock_until_dt = now + _dt.timedelta(seconds=self._lockout_duration)
            self._attempt_tracker[user_id]["locked_until"] = lock_until_dt.isoformat()
            raise MFAInvalidCodeError(
                f"Too many failed attempts. Locked for {self._lockout_duration}s."
            )

        remaining = self._max_attempts - count
        raise MFAInvalidCodeError(
            f"Invalid TOTP code. {remaining} attempt(s) remaining."
        )

    # ------------------------------------------------------------------
    # Backup Codes
    # ------------------------------------------------------------------

    def verify_backup_code(self, user_id: str, code: str) -> bool:
        """
        Verify a backup/recovery code.

        If valid, the code is consumed (single use).

        Args:
            user_id: The user's ID.
            code: Backup code from the user.

        Returns:
            True if the code was valid and consumed.
        """
        hashed = self._hash_backup_code(code)
        codes = self._backup_codes.get(user_id, set())
        if hashed in codes:
            codes.discard(hashed)
            self._backup_codes[user_id] = codes
            return True
        return False

    def regenerate_backup_codes(self, user_id: str) -> List[str]:
        """
        Generate new backup codes for a user (replaces all existing ones).

        Args:
            user_id: The user's ID.

        Returns:
            List of new backup codes.

        Raises:
            MFAInvalidCodeError: If MFA is not enabled for the user.
        """
        if user_id not in self._secrets:
            raise MFAInvalidCodeError("MFA is not enabled for this user")

        backup_codes = self._generate_backup_codes()
        hashed_codes = {self._hash_backup_code(c) for c in backup_codes}
        self._backup_codes[user_id] = hashed_codes
        return backup_codes

    # ------------------------------------------------------------------
    # MFA Disable
    # ------------------------------------------------------------------

    def is_mfa_enabled(self, user_id: str) -> bool:
        """Check if MFA is active for a user."""
        return user_id in self._secrets

    def get_pending_secret(self, user_id: str) -> Optional[str]:
        """Get the pending MFA secret (during setup)."""
        return self._pending_secrets.get(user_id)

    def disable_mfa(self, user_id: str, code: str) -> bool:
        """
        Disable MFA for a user after verifying a valid TOTP code.

        Args:
            user_id: The user's ID.
            code: Valid TOTP code for confirmation.

        Returns:
            True if MFA was successfully disabled.

        Raises:
            MFAInvalidCodeError: If the code is invalid or MFA is not enabled.
        """
        secret = self._secrets.get(user_id)
        if not secret:
            raise MFAInvalidCodeError("MFA is not enabled for this user")

        if not self.verify_code(secret, code):
            raise MFAInvalidCodeError("Invalid TOTP code")

        self._secrets.pop(user_id, None)
        self._pending_secrets.pop(user_id, None)
        self._backup_codes.pop(user_id, None)
        self._attempt_tracker.pop(user_id, None)
        return True

    def force_disable_mfa(self, user_id: str) -> bool:
        """
        Force-disable MFA for a user without code verification.
        Use this for admin overrides only.

        Args:
            user_id: The user's ID.

        Returns:
            True if MFA was disabled (or was not enabled).
        """
        removed = False
        if user_id in self._secrets:
            del self._secrets[user_id]
            removed = True
        self._pending_secrets.pop(user_id, None)
        self._backup_codes.pop(user_id, None)
        self._attempt_tracker.pop(user_id, None)
        return removed

    # ------------------------------------------------------------------
    # Storage (for persistence layer integration)
    # ------------------------------------------------------------------

    def set_secret(self, user_id: str, secret: str) -> None:
        """Directly set a user's MFA secret (e.g., loading from DB)."""
        self._secrets[user_id] = secret

    def get_secret(self, user_id: str) -> Optional[str]:
        """Get a user's active MFA secret."""
        return self._secrets.get(user_id)

    def set_backup_codes(self, user_id: str, codes: List[str]) -> None:
        """Set backup codes for a user (expects hashed codes)."""
        self._backup_codes[user_id] = {self._hash_backup_code(c) for c in codes}
