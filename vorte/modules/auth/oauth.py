"""
Vorte Auth Module - OAuth2 Providers
=====================================
Support for Google, GitHub, and generic OAuth2 authentication.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx


@dataclass
class OAuthUser:
    """Standardized OAuth user profile."""
    provider: str
    provider_id: str
    email: str
    name: str
    avatar: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


@dataclass
class OAuthConfig:
    """OAuth provider configuration."""
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: List[str] = None
    authorize_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""

    def __post_init__(self):
        if self.scopes is None:
            self.scopes = []


class OAuth2Provider:
    """Base OAuth2 provider implementation."""

    def __init__(self, config: OAuthConfig):
        self.config = config
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    @property
    def authorize_url(self) -> str:
        return self.config.authorize_url

    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """Generate the authorization redirect URL."""
        if not state:
            state = secrets.token_urlsafe(32)
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "state": state,
        }
        return f"{self.authorize_url}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        response = await self.http_client.post(self.config.token_url, data=data)
        response.raise_for_status()
        return response.json()

    async def get_user_info(self, token: str) -> OAuthUser:
        """Fetch user info from the provider. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_user_info()")

    async def close(self):
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


class GoogleOAuth2Provider(OAuth2Provider):
    """Google OAuth2 provider."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        super().__init__(OAuthConfig(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=["openid", "email", "profile"],
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://www.googleapis.com/oauth2/v2/userinfo",
        ))

    async def get_user_info(self, token: str) -> OAuthUser:
        headers = {"Authorization": f"Bearer {token}"}
        response = await self.http_client.get(
            self.config.userinfo_url, headers=headers
        )
        response.raise_for_status()
        data = response.json()
        return OAuthUser(
            provider="google",
            provider_id=data["id"],
            email=data.get("email", ""),
            name=data.get("name", ""),
            avatar=data.get("picture"),
            raw_data=data,
        )


class GitHubOAuth2Provider(OAuth2Provider):
    """GitHub OAuth2 provider."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        super().__init__(OAuthConfig(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=["user:email"],
            authorize_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            userinfo_url="https://api.github.com/user",
        ))

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": code,
        }
        response = await self.http_client.post(
            self.config.token_url,
            data=data,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return response.json()

    async def get_user_info(self, token: str) -> OAuthUser:
        # Get user profile
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        response = await self.http_client.get(
            self.config.userinfo_url, headers=headers
        )
        response.raise_for_status()
        data = response.json()

        # Get primary email
        email_response = await self.http_client.get(
            "https://api.github.com/user/emails", headers=headers
        )
        email_response.raise_for_status()
        emails = email_response.json()
        primary_email = next(
            (e["email"] for e in emails if e.get("primary")), data.get("email", "")
        )

        return OAuthUser(
            provider="github",
            provider_id=str(data["id"]),
            email=primary_email,
            name=data.get("name", data.get("login", "")),
            avatar=data.get("avatar_url"),
            raw_data=data,
        )


class OAuth2Manager:
    """Manages multiple OAuth2 providers."""

    def __init__(self):
        self._providers: Dict[str, OAuth2Provider] = {}

    def register(self, name: str, provider: OAuth2Provider) -> None:
        """Register an OAuth2 provider."""
        self._providers[name] = provider

    def get(self, name: str) -> Optional[OAuth2Provider]:
        """Get a registered provider."""
        return self._providers.get(name)

    def get_authorization_url(self, provider_name: str, state: Optional[str] = None) -> str:
        """Get the authorization URL for a provider."""
        provider = self._providers.get(provider_name)
        if not provider:
            raise ValueError(f"OAuth provider '{provider_name}' not registered")
        return provider.get_authorization_url(state)

    async def handle_callback(self, provider_name: str, code: str) -> OAuthUser:
        """Handle OAuth callback and return user info."""
        provider = self._providers.get(provider_name)
        if not provider:
            raise ValueError(f"OAuth provider '{provider_name}' not registered")
        tokens = await provider.exchange_code(code)
        access_token = tokens.get("access_token")
        return await provider.get_user_info(access_token)

    async def close_all(self):
        """Close all provider HTTP clients."""
        for provider in self._providers.values():
            await provider.close()

    def list_providers(self) -> List[str]:
        """List all registered provider names."""
        return list(self._providers.keys())
