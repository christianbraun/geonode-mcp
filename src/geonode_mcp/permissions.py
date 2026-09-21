# ABOUTTHIS: The GeoNode resource permission MCP tools -- read and change which
# ABOUTTHIS: users and groups have access, through GeoNode REST v2.
from __future__ import annotations

import time

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from geonode_mcp.geonode_call import call_geonode
from geonode_mcp.geonode_config import GeoNodeConfig
from geonode_mcp.metadata import read_resource_metadata

# A permission change is dispatched to celery, so the PATCH only says "accepted".
# Applying it takes a second or two, and a tool that returned before it landed
# would report the old permissions. So we wait -- but not forever.
POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 30.0

TERMINAL_STATES = ("finished", "failed")


def _shape(data: dict) -> dict:
    data = data or {}
    return {
        "users": data.get("users", []),
        # GeoNode splits groups in two: `groups` holds the two built-in ones,
        # `organizations` holds every group backed by a GroupProfile.
        "groups": data.get("groups", []),
        "organizations": data.get("organizations", []),
    }


def read_resource_permissions(http_client: httpx.Client, config: GeoNodeConfig, pk: int) -> dict:
    return call_geonode(
        http_client,
        config,
        "GET",
        f"/api/v2/resources/{pk}/permissions/",
        action="permissions read",
        map_result=_shape,
    )


def _execution_status(http_client: httpx.Client, config: GeoNodeConfig, execution_id: str) -> dict:
    return call_geonode(
        http_client,
        config,
        "GET",
        f"/api/v2/executionrequest/{execution_id}/",
        action="permission change status check",
        map_result=lambda data: (data or {}).get("request", {}),
    )


def write_resource_permissions(
    http_client: httpx.Client,
    config: GeoNodeConfig,
    pk: int,
    *,
    users: list[dict] | None = None,
    groups: list[dict] | None = None,
    organizations: list[dict] | None = None,
    owner: str | None = None,
) -> dict:
    """Change permissions, then wait for GeoNode to apply them and return the result.

    Each entry is `{"id": <int>, "permissions": "<level>"}`, where the level is one
    of `none`, `view`, `download`, `edit`, `manage`, `owner`. The change is merged
    into the existing spec, so anyone left out keeps what they had.

    Two group ids are special, and are what "public" and "anyone logged in" mean:
    the `anonymous` group covers users who are not signed in, and the
    `registered-members` group covers every signed-in account. Read the
    permissions first to learn their ids -- they differ between deployments.

    `owner` is a *username*, not an id, and reassigns the resource -- see
    `transfer_resource_ownership` for why this is the only route that works.
    """
    body = {}
    if users is not None:
        body["users"] = users
    if groups is not None:
        body["groups"] = groups
    if organizations is not None:
        body["organizations"] = organizations
    if owner is not None:
        body["owner"] = owner

    started = call_geonode(
        http_client,
        config,
        "PATCH",
        f"/api/v2/resources/{pk}/permissions/",
        action="permissions write",
        json=body,
        map_result=lambda data: data or {},
    )
    execution_id = started.get("execution_id")
    if not execution_id:
        raise ToolError(f"GeoNode accepted the permission change but returned no execution id: {started}")

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        request = _execution_status(http_client, config, execution_id)
        status = request.get("status")
        if status == "failed":
            raise ToolError(f"GeoNode failed to apply the permission change: {request.get('log') or request}")
        if status in TERMINAL_STATES or time.monotonic() >= deadline:
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    result = read_resource_permissions(http_client, config, pk)
    result["applied"] = status == "finished"
    if not result["applied"]:
        # Still queued. The permissions below are the old ones, so say so rather
        # than letting the caller read them as the new state.
        result["execution_id"] = execution_id
        result["status"] = status
    # A refresh during the write must still reach the caller, whichever call saw it.
    if "refreshed_tokens" in started and "refreshed_tokens" not in result:
        result["refreshed_tokens"] = started["refreshed_tokens"]
    return result


def transfer_resource_ownership(
    http_client: httpx.Client, config: GeoNodeConfig, pk: int, new_owner: str
) -> dict:
    """Hand one resource to another user, and verify GeoNode actually moved it.

    Two routes exist and only one is per-resource on GeoNode 4.4.x. The documented
    one, `POST /api/v2/users/{pk}/transfer_resources`, moves **every** resource the
    user owns in 4.4.x -- it takes no subset, so it cannot serve this. (5.0.x adds
    a `resources` list of pks and is the right route there.) So this uses the
    permissions endpoint's `owner` field, which 4.4.x forwards to
    `resource_manager.set_permissions` and 5.0.x drops on the floor.

    Because 5.0.x drops it silently, the new owner is read back rather than
    assumed: a transfer that did not happen must not be reported as one.
    """
    result = write_resource_permissions(http_client, config, pk, owner=new_owner)
    owner = read_resource_metadata(http_client, config, pk).get("owner")
    if owner != new_owner:
        raise ToolError(
            f"GeoNode did not transfer resource {pk}: it is still owned by {owner}. "
            "This route needs GeoNode 4.4.x; on 5.0.x use "
            f"POST /api/v2/users/{{pk}}/transfer_resources with resources=[{pk}]."
        )
    result["owner"] = owner
    return result


def register(server: FastMCP, http_client: httpx.Client, config: GeoNodeConfig) -> None:
    @server.tool(name="read_resource_permissions")
    def read_resource_permissions_tool(pk: int) -> dict:
        """Read a GeoNode resource's permission set (users, groups and organizations with access).

        The `anonymous` group means anyone not signed in; `registered-members`
        means every signed-in account. Their ids are needed to change them.
        """
        return read_resource_permissions(http_client, config, pk)

    @server.tool(name="write_resource_permissions")
    def write_resource_permissions_tool(
        pk: int,
        users: list[dict] | None = None,
        groups: list[dict] | None = None,
        organizations: list[dict] | None = None,
    ) -> dict:
        """Change a GeoNode resource's permissions, and wait until GeoNode has applied them.

        Entries look like {"id": 2, "permissions": "view"}. Levels: none, view,
        download, edit, manage, owner. Only what you pass is changed. To share
        with every signed-in user, grant the `registered-members` group; to make
        it public, grant the `anonymous` group. Read the permissions first to get
        their ids.

        Granting a user the `owner` level does *not* hand the resource over -
        use transfer_resource_ownership for that.
        """
        return write_resource_permissions(
            http_client, config, pk, users=users, groups=groups, organizations=organizations
        )

    @server.tool(name="transfer_resource_ownership")
    def transfer_resource_ownership_tool(pk: int, new_owner: str) -> dict:
        """Hand a GeoNode resource over to another user, who becomes its owner.

        `new_owner` is a username, not a numeric id - find_users turns a name or
        email into one. The previous owner keeps `manage` rights rather than
        losing access. Returns the resulting permission set, in which the new
        owner shows the `owner` level.

        Moves this one resource only. GeoNode's own bulk endpoint,
        /api/v2/users/{pk}/transfer_resources, moves every resource a user owns
        on 4.4.x, which is rarely what anyone means.

        Needs manage rights on the resource, which GeoNode enforces. Requires
        GeoNode 4.4.x; on 5.0.x this fails loudly rather than pretending.
        """
        return transfer_resource_ownership(http_client, config, pk, new_owner)
