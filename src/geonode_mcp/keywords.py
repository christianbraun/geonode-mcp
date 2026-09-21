# ABOUTTHIS: The "list GeoNode keywords" MCP tool -- the vocabulary an assistant
# ABOUTTHIS: needs before it can tag a resource with keywords that already exist.
from __future__ import annotations

import httpx
from fastmcp import FastMCP

from geonode_mcp.geonode_call import call_geonode
from geonode_mcp.geonode_config import GeoNodeConfig


def list_keywords(http_client: httpx.Client, config: GeoNodeConfig, query: str = "") -> dict:
    def shape(data: dict) -> dict:
        data = data or {}
        keywords = [
            {"name": k.get("name"), "slug": k.get("slug"), "resource_count": k.get("count")}
            for k in data.get("keywords", [])
        ]
        return {"total": data.get("total", len(keywords)), "keywords": keywords}

    return call_geonode(
        http_client,
        config,
        "GET",
        "/api/v2/keywords",
        action="keyword list",
        params={"search": query} if query else {},
        map_result=shape,
    )


def register(server: FastMCP, http_client: httpx.Client, config: GeoNodeConfig) -> None:
    @server.tool(name="list_keywords")
    def list_keywords_tool(query: str = "") -> dict:
        """List keywords already in use on this GeoNode, optionally filtered by a search term."""
        return list_keywords(http_client, config, query)
