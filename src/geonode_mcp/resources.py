# ABOUTTHIS: Whole-resource MCP tools -- delete a resource, and read the resources
# ABOUTTHIS: linked to and from it. Both go through /api/v2/resources.
from __future__ import annotations

import httpx
from fastmcp import FastMCP

from geonode_mcp.geonode_call import call_geonode
from geonode_mcp.geonode_config import GeoNodeConfig


def _map_linked(resource: dict) -> dict:
    return {
        "pk": resource.get("pk"),
        "title": resource.get("title"),
        "resource_type": resource.get("resource_type"),
        "detail_url": resource.get("detail_url"),
    }


def delete_resource(http_client: httpx.Client, config: GeoNodeConfig, pk: int) -> dict:
    # GeoNode answers 204 with no body on success. Maps have no DELETE on
    # /api/v2/maps, so every resource type is deleted through /api/v2/resources.
    return call_geonode(
        http_client,
        config,
        "DELETE",
        f"/api/v2/resources/{pk}/",
        action="resource delete",
        expect=(200, 202, 204),
        map_result=lambda _: {"pk": pk, "deleted": True},
    )


def get_linked_resources(http_client: httpx.Client, config: GeoNodeConfig, pk: int) -> dict:
    def shape(data: dict) -> dict:
        data = data or {}
        return {
            "linked_to": [_map_linked(r) for r in data.get("linked_to", [])],
            "linked_by": [_map_linked(r) for r in data.get("linked_by", [])],
        }

    return call_geonode(
        http_client,
        config,
        "GET",
        f"/api/v2/resources/{pk}/linked_resources",
        action="linked resources read",
        map_result=shape,
    )


def register(server: FastMCP, http_client: httpx.Client, config: GeoNodeConfig) -> None:
    @server.tool(name="delete_resource")
    def delete_resource_tool(pk: int) -> dict:
        """Delete a GeoNode resource (dataset, document or map) by primary key. Irreversible."""
        return delete_resource(http_client, config, pk)

    @server.tool(name="get_linked_resources")
    def get_linked_resources_tool(pk: int) -> dict:
        """List resources linked to and from a GeoNode resource (e.g. the datasets a map uses)."""
        return get_linked_resources(http_client, config, pk)
