# ABOUTTHIS: The "create a GeoNode map" MCP tool -- builds a map from dataset
# ABOUTTHIS: primary keys, resolving each one's alternate to a map layer.
from __future__ import annotations

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from geonode_mcp.geonode_call import call_geonode
from geonode_mcp.geonode_config import GeoNodeConfig


def _dataset_layer(http_client: httpx.Client, config: GeoNodeConfig, pk: int, order: int) -> dict:
    """One maplayer entry for a dataset pk.

    MapLayer identifies its dataset by `alternate` (workspace:name), not by pk,
    so each dataset has to be read before the map can reference it.
    """
    dataset = call_geonode(
        http_client,
        config,
        "GET",
        f"/api/v2/datasets/{pk}/",
        action=f"dataset {pk} read",
        map_result=lambda data: (data or {}).get("dataset", {}),
    )
    alternate = dataset.get("alternate")
    if not alternate:
        raise ToolError(f"Dataset {pk} has no alternate name, so it cannot be added to a map")
    return {
        "name": alternate,
        "store": dataset.get("store"),
        "order": order,
        "visibility": True,
        "opacity": 1.0,
        "extra_params": {},
    }


def create_map(
    http_client: httpx.Client,
    config: GeoNodeConfig,
    *,
    title: str,
    dataset_pks: list[int],
    abstract: str | None = None,
) -> dict:
    if not dataset_pks:
        raise ToolError("create_map needs at least one dataset pk")
    body: dict = {
        "title": title,
        "maplayers": [
            _dataset_layer(http_client, config, pk, order) for order, pk in enumerate(dataset_pks)
        ],
    }
    if abstract is not None:
        body["abstract"] = abstract

    def shape(data: dict) -> dict:
        m = (data or {}).get("map", {})
        return {
            "pk": m.get("pk"),
            "title": m.get("title"),
            "resource_type": m.get("resource_type"),
            "detail_url": m.get("detail_url"),
            "layer_count": len(m.get("maplayers", [])),
        }

    return call_geonode(
        http_client,
        config,
        "POST",
        "/api/v2/maps/",
        action="map create",
        expect=(200, 201),
        json=body,
        map_result=shape,
    )


def register(server: FastMCP, http_client: httpx.Client, config: GeoNodeConfig) -> None:
    @server.tool(name="create_map")
    def create_map_tool(title: str, dataset_pks: list[int], abstract: str | None = None) -> dict:
        """Create a GeoNode map from a list of dataset primary keys, in the given layer order."""
        return create_map(http_client, config, title=title, dataset_pks=dataset_pks, abstract=abstract)
