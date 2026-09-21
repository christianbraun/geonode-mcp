# ABOUTTHIS: The GeoNode resource metadata MCP tools -- read and edit title,
# ABOUTTHIS: abstract and keywords through GeoNode REST v2.
from __future__ import annotations

import httpx
from fastmcp import FastMCP

from geonode_mcp.geonode_call import call_geonode
from geonode_mcp.geonode_config import GeoNodeConfig


def _map_metadata(resource: dict) -> dict:
    return {
        "pk": resource.get("pk"),
        "title": resource.get("title"),
        "abstract": resource.get("abstract"),
        "resource_type": resource.get("resource_type"),
        "keywords": resource.get("keywords", []),
        "owner": (resource.get("owner") or {}).get("username"),
        "category": (resource.get("category") or {}).get("identifier"),
        "license": (resource.get("license") or {}).get("identifier"),
    }


def _shape(data: dict) -> dict:
    return _map_metadata((data or {}).get("resource", {}))


def read_resource_metadata(http_client: httpx.Client, config: GeoNodeConfig, pk: int) -> dict:
    return call_geonode(
        http_client,
        config,
        "GET",
        f"/api/v2/resources/{pk}/",
        action="metadata read",
        map_result=_shape,
    )


def write_resource_metadata(
    http_client: httpx.Client,
    config: GeoNodeConfig,
    pk: int,
    *,
    title: str | None = None,
    abstract: str | None = None,
    keywords: list[str] | None = None,
) -> dict:
    """Edit metadata. `keywords` must already exist in GeoNode -- see the note below.

    Keywords go over the wire as `[{"name": "..."}]`, never as bare strings.
    GeoNode's serializer runs `json.loads()` on a string keyword, and a plain
    word is not JSON, so the exception escapes uncaught and kills the worker --
    the caller sees a 502 from the reverse proxy rather than a 400.

    GeoNode resolves each name with `objects.get()`, so it can only *attach*
    keywords that already exist: the v2 API has no way to create one. Attaching
    an unknown name returns a clean 400. (`/api/v2/keywords` is read-only, and
    the async `/resources/{pk}/update` route that would create them raises
    TypeError in GeoNode's own dispatcher. Both hold in 4.4.x and 5.0.x.)
    """
    body = {}
    if title is not None:
        body["title"] = title
    if abstract is not None:
        body["abstract"] = abstract
    if keywords is not None:
        body["keywords"] = [{"name": keyword} for keyword in keywords]
    return call_geonode(
        http_client,
        config,
        "PATCH",
        f"/api/v2/resources/{pk}/",
        action="metadata write",
        json=body,
        map_result=_shape,
    )


def register(server: FastMCP, http_client: httpx.Client, config: GeoNodeConfig) -> None:
    @server.tool(name="read_resource_metadata")
    def read_resource_metadata_tool(pk: int) -> dict:
        """Read a GeoNode resource's metadata (title, abstract, keywords, category, license)."""
        return read_resource_metadata(http_client, config, pk)

    @server.tool(name="write_resource_metadata")
    def write_resource_metadata_tool(
        pk: int,
        title: str | None = None,
        abstract: str | None = None,
        keywords: list[str] | None = None,
    ) -> dict:
        """Edit a GeoNode resource's metadata (title, abstract, keywords). Only given fields are changed.

        Each keyword must already exist in GeoNode -- list_keywords shows which do.
        GeoNode's API cannot create a new keyword, so an unknown one is rejected.
        """
        return write_resource_metadata(http_client, config, pk, title=title, abstract=abstract, keywords=keywords)
