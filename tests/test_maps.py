# ABOUTTHIS: Integration tests at the MCP HTTP boundary for the map creation tool
# ABOUTTHIS: -- GeoNode stubbed via respx, no live instance involved.
import json

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from tests.conftest import client_for as _client_for


def _dataset(pk, alternate):
    return {"dataset": {"pk": pk, "alternate": alternate, "store": "geonode_data"}}


MAP_CREATED = {
    "map": {
        "pk": 55,
        "title": "Flood overview",
        "resource_type": "map",
        "detail_url": "/catalogue/#/map/55",
        "maplayers": [{"pk": 1}, {"pk": 2}],
    }
}


@respx.mock
async def test_create_map_resolves_alternates_and_orders_layers(app):
    respx.get("https://geonode.example/api/v2/datasets/7/").mock(
        return_value=httpx.Response(200, json=_dataset(7, "geonode:roads"))
    )
    respx.get("https://geonode.example/api/v2/datasets/8/").mock(
        return_value=httpx.Response(200, json=_dataset(8, "geonode:rivers"))
    )
    create = respx.post("https://geonode.example/api/v2/maps/").mock(
        return_value=httpx.Response(201, json=MAP_CREATED)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool(
                "create_map", {"title": "Flood overview", "dataset_pks": [7, 8]}
            )
    sent = json.loads(create.calls.last.request.read())
    assert [layer["name"] for layer in sent["maplayers"]] == ["geonode:roads", "geonode:rivers"]
    assert [layer["order"] for layer in sent["maplayers"]] == [0, 1]
    assert result.data["pk"] == 55
    assert result.data["layer_count"] == 2


@respx.mock
async def test_create_map_without_datasets_is_rejected_before_any_call(app):
    route = respx.post("https://geonode.example/api/v2/maps/")
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool("create_map", {"title": "Empty", "dataset_pks": []})
    assert not route.called


@respx.mock
async def test_create_map_fails_clearly_when_dataset_has_no_alternate(app):
    respx.get("https://geonode.example/api/v2/datasets/7/").mock(
        return_value=httpx.Response(200, json={"dataset": {"pk": 7}})
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool("create_map", {"title": "Broken", "dataset_pks": [7]})


@respx.mock
async def test_create_map_surfaces_permission_denied(app):
    respx.get("https://geonode.example/api/v2/datasets/7/").mock(
        return_value=httpx.Response(200, json=_dataset(7, "geonode:roads"))
    )
    respx.post("https://geonode.example/api/v2/maps/").mock(
        return_value=httpx.Response(403, json={"detail": "You do not have permissions."})
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool("create_map", {"title": "Denied", "dataset_pks": [7]})
