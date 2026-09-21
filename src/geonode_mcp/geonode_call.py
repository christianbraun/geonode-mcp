# ABOUTTHIS: The one request envelope every GeoNode-backed tool shares -- per-call
# ABOUTTHIS: client, OAuth error translation, status check, refreshed-token echo.
from __future__ import annotations

from typing import Any, Callable

import httpx
from fastmcp.exceptions import ToolError

from geonode_mcp.client import GeoNodeClient
from geonode_mcp.geonode_config import GeoNodeConfig
from geonode_mcp.geonode_tokens import tokens_from_request
from geonode_mcp.oauth import OAuthError, TokenPair


def call_geonode(
    http_client: httpx.Client,
    config: GeoNodeConfig,
    method: str,
    path: str,
    *,
    action: str,
    expect: tuple[int, ...] = (200,),
    map_result: Callable[[Any], dict],
    **request_kwargs,
) -> dict:
    """Make one GeoNode REST call as the calling user and shape the response.

    `action` names the operation in error messages ("search", "metadata read").
    `map_result` receives the decoded JSON body -- or None when the response has
    no body, as with a 204 from a delete -- and returns the tool's result dict.

    If GeoNode's access token expired and was refreshed mid-call, the new pair is
    added to the result under `refreshed_tokens`: MCP has no way to push
    credentials back to a client, so the client must read them off the response
    and persist them, or the next call retries a refresh_token GeoNode has
    already rotated away.
    """
    refreshed: list[TokenPair] = []
    client = GeoNodeClient(
        http_client,
        base_url=config.base_url,
        client_id=config.client_id,
        tokens=tokens_from_request(),
        on_token_refreshed=refreshed.append,
    )
    try:
        response = client.request(method, path, **request_kwargs)
    except OAuthError as exc:
        raise ToolError(f"GeoNode rejected the access token: {exc}") from exc
    if response.status_code not in expect:
        raise ToolError(f"GeoNode {action} failed: {response.status_code} {response.text}")
    result = map_result(_decode(response))
    if refreshed:
        result["refreshed_tokens"] = {
            "access_token": refreshed[-1].access_token,
            "refresh_token": refreshed[-1].refresh_token,
        }
    return result


def _decode(response: httpx.Response) -> Any:
    """Decoded JSON body, or None when there is no body (204) or it is not JSON."""
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None
