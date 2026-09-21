# ABOUTTHIS: Integration tests at the MCP HTTP boundary for the search tool --
# ABOUTTHIS: GeoNode's REST v2 response is stubbed via respx, no live instance involved.
import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from tests.conftest import client_for as _client_for

GEONODE_RESOURCES_RESPONSE = {
    "total": 1,
    "resources": [
        {
            "pk": 42,
            "title": "Wetlands 2024",
            "resource_type": "dataset",
            "state": "PROCESSED",
            "owner": {"username": "alice"},
            "detail_url": "https://geonode.example/catalogue/#/dataset/42",
        }
    ],
}


@respx.mock
async def test_search_returns_mapped_geonode_results(app):
    respx.get("https://geonode.example/api/v2/resources").mock(
        return_value=httpx.Response(200, json=GEONODE_RESOURCES_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool("search_resources", {"query": "wetlands"})
    assert result.data == {
        "total": 1,
        "resources": [
            {
                "pk": 42,
                "title": "Wetlands 2024",
                "resource_type": "dataset",
                "state": "PROCESSED",
                "owner": "alice",
                "detail_url": "https://geonode.example/catalogue/#/dataset/42",
            }
        ],
    }


async def test_search_without_mcp_bearer_token_is_rejected(app):
    async with app.lifespan(app):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with _client_for(app, mcp_token=None, geonode_tokens=("at-1", "rt-1")) as client:
                await client.call_tool("search_resources", {"query": "wetlands"})
    assert exc_info.value.response.status_code == 401


async def test_search_without_geonode_token_is_rejected(app):
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=None) as client:
            with pytest.raises(ToolError):
                await client.call_tool("search_resources", {"query": "wetlands"})


@respx.mock
async def test_search_refreshes_and_retries_once_on_401(app):
    respx.get("https://geonode.example/api/v2/resources").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json=GEONODE_RESOURCES_RESPONSE)]
    )
    respx.post("https://geonode.example/o/token/").mock(
        return_value=httpx.Response(200, json={"access_token": "at-2", "refresh_token": "rt-2"})
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool("search_resources", {"query": "wetlands"})
    assert result.data["total"] == 1
    assert result.data["refreshed_tokens"] == {"access_token": "at-2", "refresh_token": "rt-2"}


@respx.mock
async def test_search_with_rejected_geonode_token_surfaces_geonode_auth_error(app):
    respx.get("https://geonode.example/api/v2/resources").mock(return_value=httpx.Response(401))
    respx.post("https://geonode.example/o/token/").mock(return_value=httpx.Response(400, text="invalid_grant"))
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("bad-at", "bad-rt")) as client:
            with pytest.raises(ToolError):
                await client.call_tool("search_resources", {"query": "wetlands"})
