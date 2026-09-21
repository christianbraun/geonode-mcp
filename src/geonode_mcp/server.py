# ABOUTTHIS: The MCP server entrypoint. Every GeoNode tool module registers its
# ABOUTTHIS: tools on this instance.
from __future__ import annotations

import httpx
from fastmcp import FastMCP

from geonode_mcp.auth import bearer_token_verifier_from_env
from geonode_mcp.geonode_config import geonode_config_from_env
from geonode_mcp.keywords import register as register_keywords_tool
from geonode_mcp.maps import register as register_maps_tool
from geonode_mcp.metadata import register as register_metadata_tool
from geonode_mcp.permissions import register as register_permissions_tool
from geonode_mcp.resources import register as register_resources_tools
from geonode_mcp.search import register as register_search_tool
from geonode_mcp.upload import register as register_upload_tool
from geonode_mcp.users import register as register_users_tool


# httpx defaults to 5 seconds, which GeoNode routinely exceeds: creating a map
# renders a thumbnail, and an upload writes the file before answering.
REQUEST_TIMEOUT = 120.0


def create_server() -> FastMCP:
    server = FastMCP("geonode-mcp", auth=bearer_token_verifier_from_env())
    http_client = httpx.Client(timeout=REQUEST_TIMEOUT)
    config = geonode_config_from_env()
    register_search_tool(server, http_client, config)
    register_metadata_tool(server, http_client, config)
    register_permissions_tool(server, http_client, config)
    register_upload_tool(server, http_client, config)
    register_resources_tools(server, http_client, config)
    register_keywords_tool(server, http_client, config)
    register_maps_tool(server, http_client, config)
    register_users_tool(server, http_client, config)
    return server


def main() -> None:
    create_server().run(transport="http", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
