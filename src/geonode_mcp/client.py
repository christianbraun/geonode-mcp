# ABOUTTHIS: HTTP client that forwards a GeoNode OAuth2 access token as a Bearer
# ABOUTTHIS: header on every request, transparently refreshing once on a 401.
from __future__ import annotations

from typing import Callable

import httpx

from geonode_mcp.oauth import TokenPair, refresh_grant


class GeoNodeClient:
    """Forwards the caller's GeoNode access token; refreshes it once on a 401.

    `on_token_refreshed` is called with the new TokenPair whenever a refresh
    happens, so the caller can persist it back to the client's local config.
    """

    def __init__(
        self,
        http_client: httpx.Client,
        *,
        base_url: str,
        client_id: str,
        tokens: TokenPair,
        on_token_refreshed: Callable[[TokenPair], None] | None = None,
    ) -> None:
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._tokens = tokens
        self._on_token_refreshed = on_token_refreshed

    @property
    def tokens(self) -> TokenPair:
        return self._tokens

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = self._send(method, path, **kwargs)
        if response.status_code == 401:
            self._tokens = refresh_grant(
                self._http,
                base_url=self._base_url,
                client_id=self._client_id,
                refresh_token=self._tokens.refresh_token,
            )
            if self._on_token_refreshed:
                self._on_token_refreshed(self._tokens)
            response = self._send(method, path, **kwargs)
        return response

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._tokens.access_token}"
        return self._http.request(method, f"{self._base_url}{path}", headers=headers, **kwargs)
