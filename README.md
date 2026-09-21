# geonode-mcp

Talk to your GeoNode from an AI assistant. Search the catalogue, read and edit
metadata, check and change permissions, upload a dataset - in plain language,
with every action carried out **as the logged-in user**, under that user's own
GeoNode permissions.

`geonode-mcp` is an [MCP](https://modelcontextprotocol.io) server that wraps
GeoNode's REST API v2. It runs beside your GeoNode as a small companion service
and needs **no changes to GeoNode itself** - no patched templates, no forked
models, no extra Django app. If your GeoNode speaks `/api/v2/`, this works.

> **Status: working prototype.** Deployed and exercised against GeoNode 4.4.x.
> The transport, auth, and all six tools are covered by tests and verified
> end-to-end on a live instance. Not yet used in production. See
> [Limitations](#limitations) before you rely on it.

## What it looks like in practice

Once it is wired up, you ask your assistant things like:

> *"Which flood-hazard datasets do we have?"*

```
search_resources(query="flood hazard")
-> 3 results
   pk 412  Flood Hazard Zones 2024   dataset   owner: m.weber
   pk 388  Flood Depth Model         dataset   owner: a.owens
   pk 201  Flood Risk Report         document  owner: m.weber
```

> *"Give dataset 412 a proper abstract and tag it."*

```
write_resource_metadata(
  pk=412,
  abstract="Modelled 100-year flood extent for the study catchment, 2024 run.",
  keywords=["flood", "hazard", "catchment", "2024"],
)
```

> *"Who can see it? Share it with the hydrology group."*

```
read_resource_permissions(pk=412)
write_resource_permissions(pk=412, groups=[{"id": 7, "permissions": "view"}])
```

> *"Upload this GeoPackage as 'River Gauges'."*

```
upload_resource(title="River Gauges", filename="gauges.gpkg", content_base64="...")
-> execution_id: 6f4a1e2c-…, status: running
check_upload_status(execution_id="6f4a1e2c-…")
-> status: finished, resource_pks: [511]
```

Ingestion is asynchronous, so the upload hands back an execution id rather than a
resource - the resource does not exist until the import task has run.

A shapefile is a set of files, not one file, so pass the rest as `sidecar_files`:

```
upload_resource(
  title="Municipalities", filename="muni.shp", content_base64="...",
  sidecar_files=[{"filename": "muni.dbf", "content_base64": "..."},
                 {"filename": "muni.shx", "content_base64": "..."},
                 {"filename": "muni.prj", "content_base64": "..."}],
)
```

`.dbf`, `.shx` and `.prj` are required for a `.shp`; the tool refuses before
uploading rather than letting the import fail somewhere you cannot see it.

If the user asking is not allowed to see dataset 412, it simply is not in their
results. The server never sees more than they do.

## The tools

| Tool | Does | GeoNode endpoint |
|---|---|---|
| `search_resources` | Keyword search across datasets, documents, maps | `GET /api/v2/resources` |
| `read_resource_metadata` | Title, abstract, keywords, category, licence | `GET /api/v2/resources/{pk}/` |
| `write_resource_metadata` | Edit title / abstract / keywords | `PATCH /api/v2/resources/{pk}/` |
| `read_resource_permissions` | Who currently has access | `GET /api/v2/resources/{pk}/permissions/` |
| `write_resource_permissions` | Grant or revoke user/group access | `PATCH /api/v2/resources/{pk}/permissions/` |
| `upload_resource` | Start a resource upload from file content | `POST /api/v2/uploads/upload/` |
| `check_upload_status` | Poll an upload until it finishes or fails | `GET /api/v2/executionrequest/{id}/` |
| `delete_resource` | Delete a dataset, document or map | `DELETE /api/v2/resources/{pk}/` |
| `create_map` | Build a map from a list of dataset pks | `POST /api/v2/maps/` |
| `get_linked_resources` | What this resource links to, and what links to it | `GET /api/v2/resources/{pk}/linked_resources` |
| `list_keywords` | The keyword vocabulary already in use | `GET /api/v2/keywords` |
| `transfer_resource_ownership` | Hand a resource to another user | `PATCH /api/v2/resources/{pk}/permissions/` |
| `find_users` | Look up a username by name or email | `GET /api/v2/users` |

Writes only send the fields you pass, so a metadata edit will not silently blank
out everything you left out.

**Sharing with everyone** goes through two group ids GeoNode treats specially:
grant the `registered-members` group to share with every signed-in account, or
the `anonymous` group to make a resource public. Read the permissions first -
the ids differ per deployment. GeoNode applies a permission change through
celery, so `write_resource_permissions` waits for it to land and returns the
resulting spec with `applied: true`; if it is still queued you get
`applied: false` and an `execution_id` rather than a stale answer.

**Transferring ownership.** GeoNode has three routes and they behave differently:

| Route | What it does |
|---|---|
| `POST /api/v2/users/{pk}/transfer_resources` | **Documented.** Moves *every* resource that user owns on 4.4.x - it takes no subset. 5.0.x adds a `resources` list of pks and is the right route there. Staff only on 5.0.x. |
| `PATCH .../permissions/` with a user at the `owner` **level** | Documented in the endpoint's own docstring, and a no-op. Returns `200`, the execution finishes, ownership does not move: GeoNode derives owner rights from whoever the owner already is, so the grant is discarded. |
| `PATCH .../permissions/` with a top-level `owner` **username** | Undocumented, per-resource, and what actually works on 4.4.x. |

`transfer_resource_ownership` uses the third, because it is the only per-resource
route on 4.4.x, and `find_users` turns a name into the username it needs. The
previous owner is left with `manage`. Since 5.0.x drops that field silently, the
tool reads the owner back and raises rather than reporting a transfer that did
not happen.

**Keywords can only be attached, not created.** GeoNode's v2 API resolves each
keyword with an exact lookup, and offers no endpoint that creates one, so
`write_resource_metadata` can apply a keyword that already exists in the
catalogue and nothing else. `list_keywords` shows what is available. Creating a
new keyword still means the GeoNode metadata form. (Both GeoNode 4.4.x and 5.0.x;
see the [limitations](#limitations).)

`delete_resource` is the only irreversible one. It needs manage permission on the
resource, which GeoNode enforces, not this server - but nothing here asks the user
for confirmation first, so treat it as live ammunition.

## Security in one minute

Two independent layers, both required:

1. **Transport gate** - a shared `MCP_BEARER_TOKEN`. Rejects anything that is
   not your deployment before a single tool runs. It is a doorway, not an
   identity.
2. **Per-user GeoNode OAuth2** - each user brings their own access/refresh token
   pair, sent as request headers. Every GeoNode call is made **as that user**,
   so GeoNode's normal permission model applies unchanged.

There is deliberately **no service account and no admin token**. The server
holds no user credentials: it cannot act on its own, only on behalf of whoever
is calling. A user with no rights to a dataset gets nothing, whatever they ask.

Full reasoning in [docs/architecture.md](docs/architecture.md).

## Requirements

- GeoNode 4.4.x or later, reachable over **HTTPS**, with REST API v2 enabled
- Python 3.11+ (or Docker)
- Admin access to GeoNode once, to register an OAuth2 application
- An MCP-capable client (Claude Desktop, Claude Code, or any MCP client)

## Quick start

```bash
# 1. Register the OAuth2 application in GeoNode (one-time, admin)
#    See docs/setup.md - it must be a PUBLIC client with the PASSWORD grant.

# 2. Run the server
docker build -t geonode-mcp .
docker run -p 8000:8000 \
  -e GEONODE_BASE_URL=https://geonode.example.org \
  -e GEONODE_OAUTH_CLIENT_ID=<client_id from step 1> \
  -e MCP_BEARER_TOKEN=$(openssl rand -hex 32) \
  geonode-mcp

# 3. Each user, once, on their own machine
pip install git+https://github.com/christianbraun/geonode-mcp.git
geonode-mcp-setup --base-url https://geonode.example.org \
                  --client-id <client_id> --username <their username>
# prompts for password, stores tokens in ~/.geonode-mcp/tokens.json, forgets the password
```

Then point your MCP client at it. Step-by-step, including reverse proxy and
client config: **[docs/setup.md](docs/setup.md)**.

## Documentation

| Document | For |
|---|---|
| [docs/setup.md](docs/setup.md) | Operators and users: install, configure, verify, troubleshoot |
| [docs/architecture.md](docs/architecture.md) | Developers: how it is built and why |

## Limitations

Honest list, so nobody is surprised:

- **The transport token is shared.** One `MCP_BEARER_TOKEN` for every user. It
  carries no identity and cannot be revoked per person. Fine for a team; weak
  once it spreads widely. Per-user transport credentials are the obvious next
  step.
- **Password grant needs a password.** Users type their GeoNode/LDAP password
  into a local CLI once. It is posted straight to GeoNode over HTTPS and never
  stored, but sites using SSO will want an authorization-code flow instead.
- **Tokens live in a plain file** at `~/.geonode-mcp/tokens.json`, mode `0600`.
  No OS keyring integration yet.
- **Refresh rotation needs client cooperation.** When a token is refreshed
  mid-call, the new pair is returned in the response as `refreshed_tokens` and
  the client must persist it. A client that ignores this will re-send a rotated
  refresh token and eventually have to re-run setup. See
  [architecture.md](docs/architecture.md#token-refresh-and-rotation).
- **Search is keyword-only.** No spatial or temporal filtering yet, though the
  REST API supports it.
- **Uploads are base64 in-band**, so very large files are impractical.
- **New keywords cannot be created**, only existing ones attached. Two bugs in
  GeoNode itself close both routes: `PATCH /api/v2/resources/{pk}/` runs
  `json.loads()` on a string keyword and takes the worker down with it (the
  caller sees a 502), and the async `PUT /api/v2/resources/{pk}/update` route
  raises `TypeError` in GeoNode's own task dispatcher for any list argument.
  Present in 4.4.x and 5.0.x. This server sends the object form GeoNode does
  accept, so it never triggers the first one.
- **Ownership transfer is 4.4.x-only.** `transfer_resource_ownership` relies on
  the `owner` field of the permissions endpoint, which GeoNode 4.4.x forwards to
  `resource_manager.set_permissions` and 5.0.x silently drops. The tool verifies
  the owner afterwards, so on 5.0.x it fails with an error naming the route to
  use instead - `POST /api/v2/users/{pk}/transfer_resources` with a `resources`
  list, which only 5.0.x supports. No per-resource route covers both versions,
  and `owner` is read-only on the resource serializer in both.
- Tested against GeoNode 4.4.x only. GeoNode 5.x is expected to work - the v2
  API surface used here is stable - but is unverified.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest          # 61 tests, no network required
```

Every GeoNode interaction is mocked with `respx`, so the suite is offline and
fast (well under a second).

## Licence

Apache License 2.0 - see [LICENSE](LICENSE).

Copyright 2026 Christian Braun. This project contains no GeoNode source code;
it speaks to GeoNode over its public REST API v2, so GeoNode's own GPL-3.0
licence does not extend to it.
