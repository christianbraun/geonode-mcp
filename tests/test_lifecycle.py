# ABOUTTHIS: One test walking the whole resource lifecycle through the MCP boundary
# ABOUTTHIS: -- upload, poll, edit metadata, build a map, delete. GeoNode stubbed via respx.
import base64
import json

import httpx
import respx

from tests.conftest import client_for as _client_for

EXEC_ID = "6f4a1e2c-0000-4000-8000-abcdef123456"


def _part(name: str) -> dict:
    return {"filename": name, "content_base64": base64.b64encode(name.encode()).decode()}


@respx.mock
async def test_upload_edit_map_delete_round_trip(app):
    """The sequence a user actually asks for, in one session, with every GeoNode call asserted.

    Mirrors a run against a live instance: a shapefile with its sidecars becomes a
    dataset, gets a title and abstract, goes into a map, and both are deleted.
    """
    upload = respx.post("https://geonode.example/api/v2/uploads/upload/").mock(
        return_value=httpx.Response(201, json={"execution_id": EXEC_ID})
    )
    respx.get(f"https://geonode.example/api/v2/executionrequest/{EXEC_ID}/").mock(
        return_value=httpx.Response(
            200,
            json={
                "request": {
                    "exec_id": EXEC_ID,
                    "status": "finished",
                    "output_params": {"resources": [{"id": 64}]},
                }
            },
        )
    )
    patch = respx.patch("https://geonode.example/api/v2/resources/64/").mock(
        return_value=httpx.Response(
            200,
            json={
                "resource": {
                    "pk": 64,
                    "title": "Sample municipalities",
                    "abstract": "Safe to delete.",
                    "resource_type": "dataset",
                    "keywords": [],
                }
            },
        )
    )
    respx.get("https://geonode.example/api/v2/datasets/64/").mock(
        return_value=httpx.Response(
            200, json={"dataset": {"pk": 64, "alternate": "geonode:sample_municipalities"}}
        )
    )
    create_map = respx.post("https://geonode.example/api/v2/maps/").mock(
        return_value=httpx.Response(
            201,
            json={
                "map": {
                    "pk": 65,
                    "title": "Sample municipalities (map)",
                    "resource_type": "map",
                    "maplayers": [{"pk": 1}],
                }
            },
        )
    )
    respx.get("https://geonode.example/api/v2/resources/65/linked_resources").mock(
        return_value=httpx.Response(
            200,
            json={
                "linked_to": [{"pk": 64, "title": "Sample municipalities", "resource_type": "dataset"}],
                "linked_by": [],
            },
        )
    )
    delete_map = respx.delete("https://geonode.example/api/v2/resources/65/").mock(
        return_value=httpx.Response(204)
    )
    delete_dataset = respx.delete("https://geonode.example/api/v2/resources/64/").mock(
        return_value=httpx.Response(204)
    )

    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            started = await client.call_tool(
                "upload_resource",
                {
                    "title": "Sample municipalities",
                    "filename": "muni.shp",
                    "content_base64": base64.b64encode(b"shp").decode(),
                    "sidecar_files": [_part(n) for n in ("muni.dbf", "muni.shx", "muni.prj")],
                },
            )
            assert started.data["execution_id"] == EXEC_ID

            status = await client.call_tool("check_upload_status", {"execution_id": EXEC_ID})
            assert status.data["done"] is True
            pk = status.data["resource_pks"][0]

            edited = await client.call_tool(
                "write_resource_metadata",
                {"pk": pk, "title": "Sample municipalities", "abstract": "Safe to delete."},
            )
            assert edited.data["abstract"] == "Safe to delete."

            built = await client.call_tool(
                "create_map", {"title": "Sample municipalities (map)", "dataset_pks": [pk]}
            )
            assert built.data["pk"] == 65

            linked = await client.call_tool("get_linked_resources", {"pk": built.data["pk"]})
            assert [r["pk"] for r in linked.data["linked_to"]] == [pk]

            # The map first: deleting the dataset out from under it leaves a broken layer.
            assert (await client.call_tool("delete_resource", {"pk": built.data["pk"]})).data["deleted"]
            assert (await client.call_tool("delete_resource", {"pk": pk})).data["deleted"]

    assert upload.called and create_map.called
    assert delete_map.called and delete_dataset.called
    assert json.loads(patch.calls.last.request.read())["abstract"] == "Safe to delete."
