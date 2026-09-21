# ABOUTTHIS: Integration tests at the MCP HTTP boundary for the permissions-read
# ABOUTTHIS: tool -- GeoNode's REST v2 response is stubbed via respx, no live instance involved.
import json

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from geonode_mcp import permissions
from tests.conftest import client_for as _client_for

EXEC_ID = "aa11bb22-0000-4000-8000-abcdef123456"

GEONODE_PERMISSIONS_RESPONSE = {
    "users": [{"id": 1001, "username": "alice", "permissions": "owner"}],
    "organizations": [],
    "groups": [
        {"id": 3, "name": "anonymous", "permissions": "none"},
        {"id": 2, "name": "registered-members", "permissions": "view"},
    ],
}


def _mock_permission_write(*, status="finished"):
    """GeoNode answers a permission PATCH with an execution id and applies it via celery."""
    patch = respx.patch("https://geonode.example/api/v2/resources/42/permissions/").mock(
        return_value=httpx.Response(200, json={"status": "ready", "execution_id": EXEC_ID})
    )
    respx.get(f"https://geonode.example/api/v2/executionrequest/{EXEC_ID}/").mock(
        return_value=httpx.Response(200, json={"request": {"exec_id": EXEC_ID, "status": status}})
    )
    respx.get("https://geonode.example/api/v2/resources/42/permissions/").mock(
        return_value=httpx.Response(200, json=GEONODE_PERMISSIONS_RESPONSE)
    )
    return patch


@respx.mock
async def test_read_permissions_returns_geonode_permission_set(app):
    respx.get("https://geonode.example/api/v2/resources/42/permissions/").mock(
        return_value=httpx.Response(200, json=GEONODE_PERMISSIONS_RESPONSE)
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool("read_resource_permissions", {"pk": 42})
    assert result.data == GEONODE_PERMISSIONS_RESPONSE


async def test_read_permissions_without_mcp_bearer_token_is_rejected(app):
    async with app.lifespan(app):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with _client_for(app, mcp_token=None, geonode_tokens=("at-1", "rt-1")) as client:
                await client.call_tool("read_resource_permissions", {"pk": 42})
    assert exc_info.value.response.status_code == 401


async def test_read_permissions_without_geonode_token_is_rejected(app):
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=None) as client:
            with pytest.raises(ToolError):
                await client.call_tool("read_resource_permissions", {"pk": 42})


@respx.mock
async def test_write_permissions_waits_then_returns_the_applied_set(app):
    _mock_permission_write()
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool(
                "write_resource_permissions",
                {"pk": 42, "groups": [{"id": 2, "permissions": "view"}]},
            )
    assert result.data["applied"] is True
    assert result.data["groups"] == GEONODE_PERMISSIONS_RESPONSE["groups"]
    # The execution id is an implementation detail once the change has landed.
    assert "execution_id" not in result.data


@respx.mock
async def test_write_permissions_still_queued_says_so_instead_of_reporting_old_state(app, monkeypatch):
    monkeypatch.setattr(permissions, "POLL_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(permissions, "POLL_INTERVAL_SECONDS", 0)
    _mock_permission_write(status="running")
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool(
                "write_resource_permissions",
                {"pk": 42, "groups": [{"id": 2, "permissions": "view"}]},
            )
    assert result.data["applied"] is False
    assert result.data["execution_id"] == EXEC_ID


@respx.mock
async def test_write_permissions_failed_execution_is_surfaced_as_tool_error(app):
    _mock_permission_write(status="failed")
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "write_resource_permissions",
                    {"pk": 42, "groups": [{"id": 2, "permissions": "view"}]},
                )


@respx.mock
async def test_transfer_ownership_sends_the_username_as_a_top_level_owner(app):
    # The only route that actually reassigns a resource: `owner` beside the perm
    # spec, holding a username. A user granted the "owner" *level* stays a guest.
    route = _mock_permission_write()
    respx.get("https://geonode.example/api/v2/resources/42/").mock(
        return_value=httpx.Response(200, json={"resource": {"pk": 42, "owner": {"username": "alice"}}})
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            result = await client.call_tool(
                "transfer_resource_ownership", {"pk": 42, "new_owner": "alice"}
            )
    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body == {"owner": "alice"}
    assert result.data["applied"] is True
    assert result.data["owner"] == "alice"


@respx.mock
async def test_transfer_ownership_that_geonode_ignored_is_an_error_not_a_success(app):
    # GeoNode 5.0.x drops the `owner` field, answers 200 and changes nothing.
    _mock_permission_write()
    respx.get("https://geonode.example/api/v2/resources/42/").mock(
        return_value=httpx.Response(200, json={"resource": {"pk": 42, "owner": {"username": "bob"}}})
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "transfer_resource_ownership", {"pk": 42, "new_owner": "alice"}
                )


@respx.mock
async def test_write_permissions_with_only_users_does_not_clear_groups(app):
    route = _mock_permission_write()
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            await client.call_tool(
                "write_resource_permissions",
                {"pk": 42, "users": [{"id": 1001, "permissions": "owner"}]},
            )
    sent_body = json.loads(route.calls.last.request.content)
    assert "groups" not in sent_body


@respx.mock
async def test_write_permissions_permission_denied_is_surfaced_as_tool_error(app):
    respx.patch("https://geonode.example/api/v2/resources/42/permissions/").mock(
        return_value=httpx.Response(403, json={"detail": "You do not have permissions."})
    )
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=("at-1", "rt-1")) as client:
            with pytest.raises(ToolError):
                await client.call_tool("write_resource_permissions", {"pk": 42})


async def test_write_permissions_without_mcp_bearer_token_is_rejected(app):
    async with app.lifespan(app):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with _client_for(app, mcp_token=None, geonode_tokens=("at-1", "rt-1")) as client:
                await client.call_tool("write_resource_permissions", {"pk": 42})
    assert exc_info.value.response.status_code == 401


async def test_write_permissions_without_geonode_token_is_rejected(app):
    async with app.lifespan(app):
        async with _client_for(app, mcp_token="s3cret", geonode_tokens=None) as client:
            with pytest.raises(ToolError):
                await client.call_tool("write_resource_permissions", {"pk": 42})
