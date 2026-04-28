"""Vorte Authentication Module - JWT, OAuth2, API Keys, RBAC, MFA."""

from vorte.modules.auth.module import AuthModule
from vorte.modules.auth.guards import (
    IsAuthenticated,
    HasRole,
    HasPermission,
    HasApiKey,
    WithinTier,
    IsAdmin,
    ValidWebhookSignature,
    ValidSignature,
    CurrentUser,
)
from vorte.modules.auth.jwt import JWTManager
from vorte.modules.auth.api_keys import APIKeyManager
from vorte.modules.auth.rbac import RBACManager
from vorte.modules.auth.mfa import MFAManager as MFAService
from vorte.modules.auth.sessions import SessionManager
from vorte.modules.auth.models import User, Role, Permission, APIKey
from vorte.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    ForgotPasswordRequest,
)

__all__ = [
    "AuthModule",
    "IsAuthenticated",
    "HasRole",
    "HasPermission",
    "HasApiKey",
    "WithinTier",
    "IsAdmin",
    "ValidWebhookSignature",
    "ValidSignature",
    "CurrentUser",
    "JWTManager",
    "APIKeyManager",
    "RBACManager",
    "MFAService",
    "SessionManager",
    "User",
    "Role",
    "Permission",
    "APIKey",
    "LoginRequest",
    "RegisterRequest",
    "TokenResponse",
    "UserResponse",
    "PasswordResetRequest",
]
