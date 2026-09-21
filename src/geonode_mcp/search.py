# ABOUTTHIS: The "search GeoNode resources" MCP tool -- the tracer bullet proving
# ABOUTTHIS: the full request path: Layer 1 gate, Layer 2 passthrough, GeoNode REST v2, response mapping.
from __future__ import annotations

import httpx
from fastmcp import FastMCP

from geonode_mcp.geonode_call import call_geonode
from geonode_mcp.geonode_config import GeoNodeConfig


def _map_resource(resource: dict) -> dict:
    return {
        "pk": resource.get("pk"),
        "title": resource.get("title"),
        "resource_type": resource.get("resource_type"),
        "state": resource.get("state"),
        "owner": (resource.get("owner") or {}).get("username"),
        "detail_url": resource.get("detail_url"),
    }


def search_resources(http_client: httpx.Client, config: GeoNodeConfig, query: str = "") -> dict:
    def shape(data: dict) -> dict:
        data = data or {}
        resources = [_map_resource(r) for r in data.get("resources", [])]
        return {"total": data.get("total", len(resources)), "resources": resources}

    return call_geonode(
        http_client,
        config,
        "GET",
        "/api/v2/resources",
        action="search",
        params={"search": query} if query else {},
        map_result=shape,
    )


def register(server: FastMCP, http_client: httpx.Client, config: GeoNodeConfig) -> None:
    @server.tool(name="search_resources")
    def search_resources_tool(query: str = "") -> dict:
        """Search GeoNode resources (datasets, documents, maps) by keyword."""
        return search_resources(http_client, config, query)
