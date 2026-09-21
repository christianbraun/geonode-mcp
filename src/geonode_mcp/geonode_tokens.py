# ABOUTTHIS: Shared helper for pulling the caller's GeoNode OAuth2 access/refresh
# ABOUTTHIS: tokens off the MCP request headers -- used by every GeoNode-backed tool.
from __future__ import annotations

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers

from geonode_mcp.oauth import TokenPair

ACCESS_TOKEN_HEADER = "x-geonode-access-token"
REFRESH_TOKEN_HEADER = "x-geonode-refresh-token"


def tokens_from_request() -> TokenPair:
    headers = get_http_headers(include={ACCESS_TOKEN_HEADER, REFRESH_TOKEN_HEADER})
    access_token = headers.get(ACCESS_TOKEN_HEADER)
    refresh_token = headers.get(REFRESH_TOKEN_HEADER)
    if not access_token or not refresh_token:
        raise ToolError(
            f"GeoNode access token missing -- run geonode-mcp-setup and send "
            f"{ACCESS_TOKEN_HEADER}/{REFRESH_TOKEN_HEADER} headers"
        )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)
