# ABOUTTHIS: Integration tests at the MCP HTTP boundary for the user lookup tool --
# ABOUTTHIS: GeoNode's REST v2 response is stubbed via respx, no live instance involved.
import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from tests.conftest import client_for as _client_for

GEONODE_USERS_RESPONSE = {
    "total": 1,
    "users": [
        {
            "pk": 1003,
            "username": "c.nolan",
            "first_name": "Carla",
            "last_name": "Nolan",
            "email": "c.nolan@example.org",
            "avatar": "https://geonode.example/avatar.png",
        }
    ],
}

EMPTY = {"total": 0, "users": []}


@respx.mock
async def test_find_users_returns_id_and_username(app):
    route = respx.get("https://geonode.example/api/v2/users").mock(
        return_value=httpx.Response(200, json=GEONODE_USERS_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool("find_users", {"query": "nolan"})
    assert result.data["users"] == [
        {
            "id": 1003,
            "username": "c.nolan",
            "first_name": "Carla",
            "last_name": "Nolan",
            "email": "c.nolan@example.org",
        }
    ]
    # GeoNode ignores `search` on this endpoint, so the filter must be a field filter.
    assert route.calls.last.request.url.params["filter{username.icontains}"] == "nolan"


@respx.mock
async def test_find_users_falls_back_to_the_next_field_when_username_misses(app):
    route = respx.get("https://geonode.example/api/v2/users")
    route.side_effect = [
        httpx.Response(200, json=EMPTY),
        httpx.Response(200, json=GEONODE_USERS_RESPONSE),
    ]
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool("find_users", {"query": "Carla"})
    assert result.data["total"] == 1
    assert route.calls.last.request.url.params["filter{first_name.icontains}"] == "Carla"


@respx.mock
async def test_find_users_without_a_query_lists_users_unfiltered(app):
    route = respx.get("https://geonode.example/api/v2/users").mock(
        return_value=httpx.Response(200, json=GEONODE_USERS_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            await client.call_tool("find_users", {})
    assert not route.calls.last.request.url.params


async def test_find_users_without_geonode_token_is_rejected(app):
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=None) as client:
            with pytest.raises(ToolError):
                await client.call_tool("find_users", {"query": "nolan"})
