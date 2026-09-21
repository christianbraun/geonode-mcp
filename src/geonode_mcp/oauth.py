# ABOUTTHIS: OAuth2 password-grant and refresh-grant calls against GeoNode's
# ABOUTTHIS: django-oauth-toolkit /o/token/ endpoint. No credentials are cached here.
from __future__ import annotations

from dataclasses import dataclass

import httpx


class OAuthError(RuntimeError):
    """Raised when GeoNode's /o/token/ endpoint rejects a grant."""


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


def _token_pair_from_response(response: httpx.Response) -> TokenPair:
    if response.status_code != 200:
        raise OAuthError(f"GeoNode token endpoint returned {response.status_code}: {response.text}")
    data = response.json()
    return TokenPair(access_token=data["access_token"], refresh_token=data["refresh_token"])


def password_grant(
    http_client: httpx.Client,
    *,
    base_url: str,
    client_id: str,
    username: str,
    password: str,
) -> TokenPair:
    """Exchange an LDAP username/password for a GeoNode access+refresh token pair.

    The username/password are posted directly to GeoNode and never persisted.
    """
    if not base_url.startswith("https://"):
        raise OAuthError("base_url must be https:// -- refusing to send the LDAP password over plaintext HTTP")
    response = http_client.post(
        f"{base_url.rstrip('/')}/o/token/",
        data={
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": client_id,
        },
    )
    return _token_pair_from_response(response)


def refresh_grant(
    http_client: httpx.Client,
    *,
    base_url: str,
    client_id: str,
    refresh_token: str,
) -> TokenPair:
    """Exchange a refresh token for a new access+refresh token pair."""
    response = http_client.post(
        f"{base_url.rstrip('/')}/o/token/",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
    )
    return _token_pair_from_response(response)
