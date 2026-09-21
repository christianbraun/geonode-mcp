# ABOUTTHIS: Integration tests at the MCP HTTP boundary for the delete and
# ABOUTTHIS: linked-resources tools -- GeoNode stubbed via respx, no live instance.
import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from tests.conftest import client_for as _client_for

LINKED_RESPONSE = {
    "linked_to": [
        {"pk": 7, "title": "Roads", "resource_type": "dataset", "detail_url": "/catalogue/#/dataset/7"}
    ],
    "linked_by": [
        {"pk": 12, "title": "City Map", "resource_type": "map", "detail_url": "/catalogue/#/map/12"}
    ],
}


@respx.mock
async def test_delete_resource_accepts_204_with_no_body(app):
    route = respx.delete("https://geonode.example/api/v2/resources/42/").mock(
        return_value=httpx.Response(204)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool("delete_resource", {"pk": 42})
    assert route.called
    assert result.data == {"pk": 42, "deleted": True}


@respx.mock
async def test_delete_resource_without_manage_permission_is_a_tool_error(app):
    respx.delete("https://geonode.example/api/v2/resources/42/").mock(
        return_value=httpx.Response(403, json={"detail": "You do not have permissions."})
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool("delete_resource", {"pk": 42})


@respx.mock
async def test_get_linked_resources_splits_to_and_by(app):
    respx.get("https://geonode.example/api/v2/resources/12/linked_resources").mock(
        return_value=httpx.Response(200, json=LINKED_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool("get_linked_resources", {"pk": 12})
    assert [r["pk"] for r in result.data["linked_to"]] == [7]
    assert [r["pk"] for r in result.data["linked_by"]] == [12]


async def test_delete_resource_without_mcp_bearer_token_is_rejected(app):
    async with app.lifespan(app):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with _client_for(app, mcp_token=None, geonode_tokens=("at-1", "rt-1")) as client:
                await client.call_tool("delete_resource", {"pk": 42})
    assert exc_info.value.response.status_code == 401
