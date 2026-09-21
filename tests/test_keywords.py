# ABOUTTHIS: Integration tests at the MCP HTTP boundary for the keyword list tool
# ABOUTTHIS: -- GeoNode stubbed via respx, no live instance involved.
import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from tests.conftest import client_for as _client_for

KEYWORDS_RESPONSE = {
    "total": 2,
    "keywords": [
        {"name": "hydrology", "slug": "hydrology", "count": 14},
        {"name": "landcover", "slug": "landcover", "count": 3},
    ],
}


@respx.mock
async def test_list_keywords_maps_name_slug_and_count(app):
    respx.get("https://geonode.example/api/v2/keywords").mock(
        return_value=httpx.Response(200, json=KEYWORDS_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool("list_keywords", {})
    assert result.data["total"] == 2
    assert result.data["keywords"][0] == {"name": "hydrology", "slug": "hydrology", "resource_count": 14}


@respx.mock
async def test_list_keywords_passes_search_term(app):
    route = respx.get("https://geonode.example/api/v2/keywords").mock(
        return_value=httpx.Response(200, json={"total": 0, "keywords": []})
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            await client.call_tool("list_keywords", {"query": "hydro"})
    assert route.calls.last.request.url.params["search"] == "hydro"


@respx.mock
async def test_list_keywords_error_is_surfaced_as_tool_error(app):
    respx.get("https://geonode.example/api/v2/keywords").mock(
        return_value=httpx.Response(500, text="boom")
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool("list_keywords", {})
