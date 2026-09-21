# ABOUTTHIS: Integration tests at the MCP HTTP boundary for the upload tool --
# ABOUTTHIS: GeoNode's REST v2 response is stubbed via respx, no live instance involved.
import base64

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from tests.conftest import client_for as _client_for

# What geonode-importer actually answers with: an execution id, no resource. The
# resource does not exist yet -- ingestion is asynchronous.
GEONODE_UPLOAD_RESPONSE = {"execution_id": "6f4a1e2c-0000-4000-8000-abcdef123456"}

EXECUTION_FINISHED = {
    "request": {
        "exec_id": "6f4a1e2c-0000-4000-8000-abcdef123456",
        "status": "finished",
        "step": "importer.publish_resource",
        "created": "2026-07-28T06:00:00Z",
        "finished": "2026-07-28T06:00:42Z",
        "output_params": {"resources": [{"id": 99}]},
        "log": None,
    }
}


@respx.mock
async def test_upload_returns_execution_id_to_poll(app):
    respx.post("https://geonode.example/api/v2/uploads/upload/").mock(
        return_value=httpx.Response(201, json=GEONODE_UPLOAD_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool(
                "upload_resource",
                {
                    "title": "New Dataset",
                    "filename": "data.geojson",
                    "content_base64": base64.b64encode(b"{}").decode(),
                },
            )
    assert result.data["execution_id"] == "6f4a1e2c-0000-4000-8000-abcdef123456"
    assert result.data["status"] == "running"


@respx.mock
async def test_check_upload_status_reports_finished_with_resource_pks(app):
    respx.get(
        "https://geonode.example/api/v2/executionrequest/6f4a1e2c-0000-4000-8000-abcdef123456/"
    ).mock(return_value=httpx.Response(200, json=EXECUTION_FINISHED))
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool(
                "check_upload_status",
                {"execution_id": "6f4a1e2c-0000-4000-8000-abcdef123456"},
            )
    assert result.data["status"] == "finished"
    assert result.data["done"] is True
    assert result.data["resource_pks"] == [99]


@respx.mock
async def test_check_upload_status_running_is_not_done(app):
    respx.get(
        "https://geonode.example/api/v2/executionrequest/6f4a1e2c-0000-4000-8000-abcdef123456/"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"request": {"status": "running", "step": "importer.import_resource", "output_params": {}}},
        )
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool(
                "check_upload_status",
                {"execution_id": "6f4a1e2c-0000-4000-8000-abcdef123456"},
            )
    assert result.data["done"] is False
    assert result.data["resource_pks"] == []


def _part(name: str) -> dict:
    return {"filename": name, "content_base64": base64.b64encode(name.encode()).decode()}


@respx.mock
async def test_shapefile_sidecars_go_to_their_own_importer_fields(app):
    route = respx.post("https://geonode.example/api/v2/uploads/upload/").mock(
        return_value=httpx.Response(201, json=GEONODE_UPLOAD_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            await client.call_tool(
                "upload_resource",
                {
                    "title": "Municipalities",
                    "filename": "muni.shp",
                    "content_base64": base64.b64encode(b"shp").decode(),
                    # .cpg is not an importer field and must be dropped, not forwarded.
                    "sidecar_files": [_part(n) for n in ("muni.dbf", "muni.shx", "muni.prj", "muni.cpg")],
                },
            )
    body = route.calls.last.request.read().decode("latin-1")
    for field in ("base_file", "dbf_file", "shx_file", "prj_file"):
        assert f'name="{field}"' in body
    assert "muni.cpg" not in body


@respx.mock
async def test_shapefile_without_sidecars_is_rejected_before_any_call(app):
    route = respx.post("https://geonode.example/api/v2/uploads/upload/")
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "upload_resource",
                    {
                        "title": "Municipalities",
                        "filename": "muni.shp",
                        "content_base64": base64.b64encode(b"shp").decode(),
                    },
                )
    assert not route.called


@respx.mock
async def test_upload_permission_denied_is_surfaced_as_tool_error(app):
    respx.post("https://geonode.example/api/v2/uploads/upload/").mock(
        return_value=httpx.Response(403, json={"detail": "You do not have permissions."})
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "upload_resource",
                    {
                        "title": "New Dataset",
                        "filename": "data.geojson",
                        "content_base64": base64.b64encode(b"{}").decode(),
                    },
                )


async def test_upload_without_mcp_bearer_token_is_rejected(app):
    async with app.lifespan(app):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with _client_for(app, mcp_token=None, geonode_tokens=("at-1", "rt-1")) as client:
                await client.call_tool(
                    "upload_resource",
                    {
                        "title": "New Dataset",
                        "filename": "data.geojson",
                        "content_base64": base64.b64encode(b"{}").decode(),
                    },
                )
    assert exc_info.value.response.status_code == 401


async def test_upload_without_geonode_token_is_rejected(app):
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=None) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "upload_resource",
                    {
                        "title": "New Dataset",
                        "filename": "data.geojson",
                        "content_base64": base64.b64encode(b"{}").decode(),
                    },
                )
