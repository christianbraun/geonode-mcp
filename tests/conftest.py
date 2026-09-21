# ABOUTTHIS: Shared MCP test client helper -- wires an in-process fastmcp Client
# ABOUTTHIS: to the app's ASGI transport with Layer 1/2 auth headers set as needed.
import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from geonode_mcp.geonode_tokens import ACCESS_TOKEN_HEADER, REFRESH_TOKEN_HEADER
from geonode_mcp.server import create_server


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "s3cret")
    monkeypatch.setenv("GEONODE_BASE_URL", "https://geonode.example")
    monkeypatch.setenv("GEONODE_OAUTH_CLIENT_ID", "cid")
    return create_server().http_app()


def client_for(app, *, mcp_token: str | None, geonode_tokens: tuple[str, str] | None) -> Client:
    def http_client_factory(headers=None, timeout=None, auth=None, **kwargs):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers=headers,
            timeout=timeout,
            auth=auth,
            **kwargs,
        )

    extra_headers = {}
    if geonode_tokens is not None:
        access_token, refresh_token = geonode_tokens
        extra_headers[ACCESS_TOKEN_HEADER] = access_token
        extra_headers[REFRESH_TOKEN_HEADER] = refresh_token

    transport = StreamableHttpTransport(
        "http://testserver/mcp/",
        auth=mcp_token,
        headers=extra_headers,
        httpx_client_factory=http_client_factory,
    )
    return Client(transport)
