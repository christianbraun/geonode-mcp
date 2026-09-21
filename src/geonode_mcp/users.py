# ABOUTTHIS: The "find GeoNode users" MCP tool -- turns a name or email fragment
# ABOUTTHIS: into the username and id that the permission tools need.
from __future__ import annotations

import httpx
from fastmcp import FastMCP

from geonode_mcp.geonode_call import call_geonode
from geonode_mcp.geonode_config import GeoNodeConfig

# GeoNode's user list ignores `search`, so filtering goes through dynamic_rest's
# field filters. There is no OR across fields, hence one request per field until
# something matches.
SEARCH_FIELDS = ("username", "first_name", "last_name", "email")


def _shape(data: dict) -> dict:
    data = data or {}
    users = [
        {
            "id": u.get("pk"),
            "username": u.get("username"),
            "first_name": u.get("first_name"),
            "last_name": u.get("last_name"),
            "email": u.get("email"),
        }
        for u in data.get("users", [])
    ]
    return {"total": data.get("total", len(users)), "users": users}


def find_users(http_client: httpx.Client, config: GeoNodeConfig, query: str = "") -> dict:
    if not query:
        return call_geonode(http_client, config, "GET", "/api/v2/users", action="user list", map_result=_shape)

    result = {"total": 0, "users": []}
    for field in SEARCH_FIELDS:
        result = call_geonode(
            http_client,
            config,
            "GET",
            "/api/v2/users",
            action="user search",
            params={f"filter{{{field}.icontains}}": query},
            map_result=_shape,
        )
        if result["users"]:
            break
    return result


def register(server: FastMCP, http_client: httpx.Client, config: GeoNodeConfig) -> None:
    @server.tool(name="find_users")
    def find_users_tool(query: str = "") -> dict:
        """Find GeoNode users by a fragment of their username, name or email.

        Returns each match's `id` and `username` - the id is what the permission
        tools take, the username is what transfer_resource_ownership takes. With
        no query, lists users. Only what the caller is allowed to see.
        """
        return find_users(http_client, config, query)
