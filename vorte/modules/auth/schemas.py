"""
Vorte Auth Schemas
==================
Pydantic v2 schemas for request validation and response serialization
across the authentication module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    """Schema for user registration."""
    email: EmailStr
    username: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v


class RegisterResponse(BaseModel):
    """Schema returned after successful registration."""
    id: str
    email: str
    username: str
    email_verified: bool = False
    message: str = "Registration successful. Please check your email to verify your account."


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Schema for email/password login."""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Schema returned after successful login."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    user: Dict[str, Any]
    mfa_required: bool = False


class MFAChallengeRequest(BaseModel):
    """Schema for submitting a TOTP code during MFA verification."""
    user_id: str
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


# ---------------------------------------------------------------------------
# Token / Refresh
# ---------------------------------------------------------------------------

class RefreshRequest(BaseModel):
    """Schema for refreshing an access token."""
    refresh_token: str


class TokenResponse(BaseModel):
    """Schema for token responses."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    """Internal representation of a decoded JWT payload."""
    sub: str = Field(description="User ID")
    email: str
    roles: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    tier: str = "free"
    mfa_verified: bool = False
    type: str = "access"
    exp: int
    iat: int
    jti: Optional[str] = None


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    """Schema for user profile responses."""
    id: str
    email: str
    username: str
    status: str
    roles: List[str]
    permissions: List[str]
    mfa_enabled: bool
    email_verified: bool
    avatar_url: str = ""
    tier: str
    last_login_at: Optional[str] = None
    created_at: str


class UpdateProfileRequest(BaseModel):
    """Schema for updating user profile."""
    username: Optional[str] = Field(None, min_length=2, max_length=64)
    avatar_url: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    """Schema for changing the user's password."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    """Schema for requesting a password reset email."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Schema for setting a new password using a reset token."""
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


# ---------------------------------------------------------------------------
# Email Verification
# ---------------------------------------------------------------------------

class VerifyEmailRequest(BaseModel):
    """Schema for verifying an email with a token."""
    token: str


# ---------------------------------------------------------------------------
# MFA
# ---------------------------------------------------------------------------

class MFASetupResponse(BaseModel):
    """Schema returned when setting up MFA."""
    secret: str = Field(description="TOTP secret (show to user once for QR code)")
    qr_code_url: str = Field(description="OTPAuth URI for QR code generation")
    backup_codes: List[str] = Field(description="Recovery codes for emergency access")


class MFAVerifyRequest(BaseModel):
    """Schema for verifying MFA setup with a TOTP code."""
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class MFADisableRequest(BaseModel):
    """Schema for disabling MFA (requires password confirmation)."""
    password: str
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------

class OAuthCallbackRequest(BaseModel):
    """Schema for OAuth callback handling."""
    provider: str
    code: str
    redirect_uri: Optional[str] = None
    state: Optional[str] = None


class OAuthLinkRequest(BaseModel):
    """Schema for linking an OAuth provider to an existing account."""
    provider: str
    access_token: str


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

class CreateAPIKeyRequest(BaseModel):
    """Schema for creating a new API key."""
    name: str = Field(..., min_length=1, max_length=128)
    scopes: List[str] = Field(default_factory=lambda: ["read"])
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)
    rate_limit: int = Field(0, ge=0, description="Max requests per minute (0 = unlimited)")


class APIKeyResponse(BaseModel):
    """Schema for API key responses."""
    id: str
    name: str
    key: str = Field(description="Full API key (shown only on creation)")
    key_prefix: str
    scopes: List[str]
    status: str
    expires_at: Optional[str] = None
    rate_limit: int
    created_at: str


class APIKeyInfoResponse(BaseModel):
    """Schema for API key info (without the raw key)."""
    id: str
    name: str
    key_prefix: str
    scopes: List[str]
    status: str
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    rate_limit: int
    created_at: str


# ---------------------------------------------------------------------------
# Roles & Permissions
# ---------------------------------------------------------------------------

class CreateRoleRequest(BaseModel):
    """Schema for creating a new role."""
    name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9_-]+$")
    description: str = ""
    permissions: List[str] = Field(default_factory=list)
    is_default: bool = False
    priority: int = 0


class UpdateRoleRequest(BaseModel):
    """Schema for updating a role."""
    description: Optional[str] = None
    permissions: Optional[List[str]] = None
    is_default: Optional[bool] = None
    priority: Optional[int] = None


class AssignRoleRequest(BaseModel):
    """Schema for assigning a role to a user."""
    user_id: str
    role_name: str


class RoleResponse(BaseModel):
    """Schema for role responses."""
    name: str
    description: str
    permissions: List[str]
    is_default: bool
    priority: int
    user_count: int = 0


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class SessionResponse(BaseModel):
    """Schema for session information."""
    session_id: str
    user_id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: str
    last_activity: str
    is_current: bool = False


# ---------------------------------------------------------------------------
# Generic / Error
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    """Simple message response schema."""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    error: str
    code: str
    details: Optional[Any] = None
