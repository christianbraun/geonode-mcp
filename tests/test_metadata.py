# ABOUTTHIS: Integration tests at the MCP HTTP boundary for the metadata-read
# ABOUTTHIS: tool -- GeoNode's REST v2 response is stubbed via respx, no live instance involved.
import json

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from tests.conftest import client_for as _client_for

GEONODE_RESOURCE_RESPONSE = {
    "resource": {
        "pk": 42,
        "title": "Wetlands 2024",
        "abstract": "Wetland boundaries for the 2024 survey.",
        "resource_type": "dataset",
        "keywords": ["wetlands", "2024"],
        "owner": {"username": "alice"},
        "category": {"identifier": "environment"},
        "license": {"identifier": "CC-BY-4.0"},
    }
}


@respx.mock
async def test_read_metadata_returns_mapped_geonode_resource(app):
    respx.get("https://geonode.example/api/v2/resources/42/").mock(
        return_value=httpx.Response(200, json=GEONODE_RESOURCE_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool("read_resource_metadata", {"pk": 42})
    assert result.data == {
        "pk": 42,
        "title": "Wetlands 2024",
        "abstract": "Wetland boundaries for the 2024 survey.",
        "resource_type": "dataset",
        "keywords": ["wetlands", "2024"],
        "owner": "alice",
        "category": "environment",
        "license": "CC-BY-4.0",
    }


async def test_read_metadata_without_mcp_bearer_token_is_rejected(app):
    async with app.lifespan(app):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with _client_for(app, mcp_token=None, geonode_tokens=("at-1", "rt-1")) as client:
                await client.call_tool("read_resource_metadata", {"pk": 42})
    assert exc_info.value.response.status_code == 401


async def test_read_metadata_without_geonode_token_is_rejected(app):
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=None) as client:
            with pytest.raises(ToolError):
                await client.call_tool("read_resource_metadata", {"pk": 42})


@respx.mock
async def test_write_metadata_returns_mapped_geonode_resource(app):
    respx.patch("https://geonode.example/api/v2/resources/42/").mock(
        return_value=httpx.Response(200, json=GEONODE_RESOURCE_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool("write_resource_metadata", {"pk": 42, "title": "Wetlands 2024"})
    assert result.data["title"] == "Wetlands 2024"


@respx.mock
async def test_write_metadata_sends_keywords_as_objects_not_bare_strings(app):
    """A bare string keyword makes GeoNode's serializer json.loads() it and die with a 502."""
    route = respx.patch("https://geonode.example/api/v2/resources/42/").mock(
        return_value=httpx.Response(200, json=GEONODE_RESOURCE_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            await client.call_tool(
                "write_resource_metadata", {"pk": 42, "keywords": ["wetlands", "2024"]}
            )
    sent = json.loads(route.calls.last.request.read())
    assert sent["keywords"] == [{"name": "wetlands"}, {"name": "2024"}]


@respx.mock
async def test_write_metadata_permission_denied_is_surfaced_as_tool_error(app):
    respx.patch("https://geonode.example/api/v2/resources/42/").mock(
        return_value=httpx.Response(403, json={"detail": "You do not have permissions."})
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool("write_resource_metadata", {"pk": 42, "title": "Wetlands 2024"})


async def test_write_metadata_without_mcp_bearer_token_is_rejected(app):
    async with app.lifespan(app):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with _client_for(app, mcp_token=None, geonode_tokens=("at-1", "rt-1")) as client:
                await client.call_tool("write_resource_metadata", {"pk": 42, "title": "x"})
    assert exc_info.value.response.status_code == 401


async def test_write_metadata_without_geonode_token_is_rejected(app):
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=None) as client:
            with pytest.raises(ToolError):
                await client.call_tool("write_resource_metadata", {"pk": 42, "title": "x"})
