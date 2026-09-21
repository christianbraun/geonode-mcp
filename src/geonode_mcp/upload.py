# ABOUTTHIS: Upload MCP tools -- push a file into GeoNode, and poll the resulting
# ABOUTTHIS: execution request until ingestion finishes.
from __future__ import annotations

import base64

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from geonode_mcp.geonode_call import call_geonode
from geonode_mcp.geonode_config import GeoNodeConfig

TERMINAL_STATES = ("finished", "failed")

# geonode-importer takes each part of a multi-file format in its own multipart
# field, named after the extension. Anything not listed here is rejected by the
# importer's serializer, so there is no point forwarding it.
SIDECAR_FIELDS = {
    "dbf": "dbf_file",
    "shx": "shx_file",
    "prj": "prj_file",
    "xml": "xml_file",
    "sld": "sld_file",
}

# A shapefile is not a file, it is a set. The importer's ShapeFileSerializer
# marks all four required, and a missing one fails deep inside the async task
# where the caller cannot see why.
SHAPEFILE_REQUIRED = ("dbf_file", "shx_file", "prj_file")


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def upload_resource(
    http_client: httpx.Client,
    config: GeoNodeConfig,
    *,
    title: str,
    filename: str,
    content_base64: str,
    sidecar_files: list[dict] | None = None,
) -> dict:
    """Start an upload. Ingestion is asynchronous -- poll with check_upload_status.

    `filename`/`content_base64` are the main file. Formats made of several files
    (a shapefile's .dbf/.shx/.prj) pass the rest as `sidecar_files`, each a
    `{"filename": ..., "content_base64": ...}` dict; each one is routed to the
    importer field its extension implies.

    GeoNode core's own upload endpoint is a stub; geonode-importer overrides the
    route and answers with an execution id, not a resource, because the resource
    does not exist until the import task has actually run.
    """
    files = {"base_file": (filename, base64.b64decode(content_base64))}
    for sidecar in sidecar_files or []:
        name = sidecar.get("filename", "")
        field = SIDECAR_FIELDS.get(_extension(name))
        if not field:
            # .cpg and friends: harmless to hold back, fatal to forward.
            continue
        files[field] = (name, base64.b64decode(sidecar["content_base64"]))

    if _extension(filename) == "shp":
        missing = [f for f in SHAPEFILE_REQUIRED if f not in files]
        if missing:
            raise ToolError(
                f"Shapefile upload needs its sidecar files -- missing {', '.join(missing)}. "
                f"Pass the .dbf, .shx and .prj as sidecar_files."
            )

    return call_geonode(
        http_client,
        config,
        "POST",
        "/api/v2/uploads/upload/",
        action="upload",
        expect=(200, 201),
        data={"title": title},
        files=files,
        map_result=lambda data: {
            "execution_id": (data or {}).get("execution_id"),
            "status": "running",
            "next": "Poll check_upload_status with this execution_id until status is finished or failed.",
        },
    )


def check_upload_status(http_client: httpx.Client, config: GeoNodeConfig, execution_id: str) -> dict:
    def shape(data: dict) -> dict:
        request = (data or {}).get("request", {})
        status = request.get("status")
        resources = (request.get("output_params") or {}).get("resources", [])
        return {
            "execution_id": request.get("exec_id", execution_id),
            "status": status,
            "done": status in TERMINAL_STATES,
            "step": request.get("step"),
            "created": request.get("created"),
            "finished": request.get("finished"),
            # Populated only once the import succeeded; a failure carries `log` instead.
            "resource_pks": [pk for pk in (r.get("id") or r.get("pk") for r in resources) if pk is not None],
            "log": request.get("log"),
        }

    return call_geonode(
        http_client,
        config,
        "GET",
        f"/api/v2/executionrequest/{execution_id}/",
        action="upload status check",
        map_result=shape,
    )


def register(server: FastMCP, http_client: httpx.Client, config: GeoNodeConfig) -> None:
    @server.tool(name="upload_resource")
    def upload_resource_tool(
        title: str,
        filename: str,
        content_base64: str,
        sidecar_files: list[dict] | None = None,
    ) -> dict:
        """Upload a new GeoNode resource from base64 file content. Returns an execution_id to poll.

        A shapefile must pass its .dbf, .shx and .prj as sidecar_files, each
        {"filename": ..., "content_base64": ...}.
        """
        return upload_resource(
            http_client,
            config,
            title=title,
            filename=filename,
            content_base64=content_base64,
            sidecar_files=sidecar_files,
        )

    @server.tool(name="check_upload_status")
    def check_upload_status_tool(execution_id: str) -> dict:
        """Check an upload's progress by execution_id. Returns status, and resource pks once finished."""
        return check_upload_status(http_client, config, execution_id)
