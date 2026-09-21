# ABOUTTHIS: Layer 1 bearer gate -- correct MCP_BEARER_TOKEN reaches the tool
# ABOUTTHIS: layer, a missing or wrong one is rejected before any tool runs.
import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from geonode_mcp.auth import MissingBearerTokenError, bearer_token_verifier_from_env
from geonode_mcp.server import create_server


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "s3cret")
    monkeypatch.setenv("GEONODE_BASE_URL", "https://geonode.example")
    monkeypatch.setenv("GEONODE_OAUTH_CLIENT_ID", "cid")
    server = create_server()
    server.tool(lambda: "pong", name="ping")
    return server.http_app()


def _client_for(app, token: str | None) -> Client:
    def http_client_factory(headers=None, timeout=None, auth=None, **kwargs):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers=headers,
            timeout=timeout,
            auth=auth,
            **kwargs,
        )

    transport = StreamableHttpTransport(
        "http://testserver/mcp/",
        auth=token,
        httpx_client_factory=http_client_factory,
    )
    return Client(transport)


async def test_correct_token_reaches_tool_layer(app):
    async with app.lifespan(app):
        async with _client_for(app, "s3cret") as client:
            result = await client.call_tool("ping", {})
    assert result.content[0].text == "pong"


async def test_missing_token_is_rejected(app):
    async with app.lifespan(app):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with _client_for(app, None) as client:
                await client.call_tool("ping", {})
    assert exc_info.value.response.status_code == 401


async def test_wrong_token_is_rejected(app):
    async with app.lifespan(app):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with _client_for(app, "wrong") as client:
                await client.call_tool("ping", {})
    assert exc_info.value.response.status_code == 401


def test_missing_env_var_raises(monkeypatch):
    monkeypatch.delenv("MCP_BEARER_TOKEN", raising=False)
    with pytest.raises(MissingBearerTokenError):
        bearer_token_verifier_from_env()
