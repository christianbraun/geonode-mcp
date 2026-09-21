# Setup guide

From nothing to a working assistant connection. Steps 1 to 3 are done once by an
administrator; step 4 is done by each user on their own machine.

**Before you start you need:** a GeoNode 4.4.x+ instance reachable over HTTPS
with REST API v2 enabled, admin access to it once, somewhere to run a container
next to it, and an MCP-capable client.

---

## Step 1 - Register the OAuth2 application (admin, once)

`geonode-mcp` needs an OAuth2 application in GeoNode so users can exchange their
credentials for tokens. It must be a **public client** using the **password**
grant.

Via the Django shell:

```bash
docker exec <geonode-django-container> python3 manage.py shell -c "
from oauth2_provider.models import get_application_model
App = get_application_model()
app, created = App.objects.get_or_create(
    name='geonode-mcp',
    defaults={
        'client_type': 'public',
        'authorization_grant_type': 'password',
        'skip_authorization': False,
    },
)
print('client_id:', app.client_id)
print('created:', created)
"
```

Or through the admin UI at `/admin/oauth2_provider/application/`: *Add*,
name `geonode-mcp`, client type **Public**, grant type **Resource owner
password-based**.

**Write down the `client_id`.** Both the server and every user need it. It is an
identifier, not a secret - a public client has no secret by design.

Verify it took:

```bash
docker exec <geonode-django-container> python3 manage.py shell -c "
from oauth2_provider.models import get_application_model as A
a = A().objects.get(name='geonode-mcp')
print(a.client_type, a.authorization_grant_type)
"
# expect: public password
```

---

## Step 2 - Run the server (admin)

### Configuration

Three environment variables, all required. The server refuses to start without
them, rather than starting and failing per request.

| Variable | Meaning | Example |
|---|---|---|
| `GEONODE_BASE_URL` | Your GeoNode, **https only** | `https://geonode.example.org` |
| `GEONODE_OAUTH_CLIENT_ID` | `client_id` from step 1 | `xY3k...` (40 chars) |
| `MCP_BEARER_TOKEN` | Shared transport secret you generate | `openssl rand -hex 32` |

> **`GEONODE_OAUTH_CLIENT_ID` must match step 1 exactly.** A mismatch is the
> single most common failure, and an unpleasant one: setup fails for every user
> with `invalid_client`, and token refresh breaks too, so even a working session
> dies at expiry. Verify with the command in [Troubleshooting](#invalid_client).

### With docker compose

```yaml
services:
  mcp:
    image: geonode-mcp:latest
    build: ./mcp
    container_name: mcp
    restart: unless-stopped
    environment:
      - GEONODE_BASE_URL=https://geonode.example.org
      - GEONODE_OAUTH_CLIENT_ID=<client_id from step 1>
      - MCP_BEARER_TOKEN=<your generated secret>
```

Deliberately **no `ports:` entry** - the service should not be published to the
host. Reach it through the reverse proxy in step 3, so it inherits GeoNode's TLS.

### Standalone

```bash
pip install git+https://github.com/christianbraun/geonode-mcp.git
GEONODE_BASE_URL=https://geonode.example.org \
GEONODE_OAUTH_CLIENT_ID=<client_id> \
MCP_BEARER_TOKEN=<secret> \
python -m geonode_mcp.server
```

---

## Step 3 - Expose it through your reverse proxy (admin)

nginx, alongside your existing GeoNode config:

```nginx
location /mcp {
  set $upstream mcp:8000;

  proxy_redirect              off;
  proxy_set_header            Host $host;
  proxy_set_header            X-Real-IP $remote_addr;
  proxy_set_header            X-Forwarded-Host $server_name;
  proxy_set_header            X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header            X-Forwarded-Proto https;

  proxy_pass http://$upstream;
}
```

Three things here are load-bearing:

- **`location /mcp` has no trailing slash.** With `location /mcp/`, nginx
  auto-301s `/mcp` to `/mcp/`, FastMCP 307s `/mcp/` back to `/mcp`, and requests
  bounce between them forever. This costs an afternoon to diagnose.
- **`proxy_pass` has no URI part** either, so the path is forwarded unchanged.
- **`set $upstream`** defers DNS to request time. A literal hostname in
  `proxy_pass` is resolved when the config loads, so nginx refuses to start if
  the MCP container is not up yet. Requires a `resolver` directive (in Docker,
  `resolver 127.0.0.11;`).

Check it:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://geonode.example.org/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

**`401` is the correct answer** - you sent no bearer token, and the gate stopped
you. That proves routing and the auth layer are both alive. `404` means the
location is not applied; `301`/`307` means the trailing-slash loop.

---

## Step 4 - Per-user setup (each user, once)

On their own machine:

```bash
pip install git+https://github.com/christianbraun/geonode-mcp.git

geonode-mcp-setup \
  --base-url https://geonode.example.org \
  --client-id <client_id from step 1> \
  --username <their GeoNode/LDAP username>
```

It prompts for the password, exchanges it for a token pair, writes
`~/.geonode-mcp/tokens.json` (mode `0600`), and discards the password. Nothing
sends the password anywhere except GeoNode's own token endpoint, over HTTPS.

**No admin rights needed.** Any user with a GeoNode account can do this, and
gets exactly their own permissions - no more.

Confirm:

```bash
ls -l ~/.geonode-mcp/tokens.json    # -rw------- , 0600
```

### Configure the MCP client

Both tokens go in the client's header config. For Claude Desktop
(`claude_desktop_config.json`) or Claude Code (`.mcp.json`):

```json
{
  "mcpServers": {
    "geonode": {
      "type": "http",
      "url": "https://geonode.example.org/mcp",
      "headers": {
        "Authorization": "Bearer <MCP_BEARER_TOKEN from step 2>",
        "x-geonode-access-token": "<access_token from tokens.json>",
        "x-geonode-refresh-token": "<refresh_token from tokens.json>"
      }
    }
  }
}
```

All three headers are required: the first is the shared door key, the other two
are the user's identity.

Restart the client, then try: *"Search GeoNode for flood datasets."*

---

## Verifying the whole chain

Run these in order; each isolates one layer.

```bash
BASE=https://geonode.example.org
BEARER=<MCP_BEARER_TOKEN>
ACCESS=<access_token>
REFRESH=<refresh_token>

# 1. Gate rejects an unauthenticated call -> expect 401
curl -s -o /dev/null -w "no token:  %{http_code}\n" -X POST $BASE/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

# 2. Handshake with the bearer -> expect 200 and serverInfo
curl -s -X POST $BASE/mcp \
  -H "Authorization: Bearer $BEARER" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}'
```

A successful handshake returns the session id in the `Mcp-Session-Id` response
header; subsequent calls need it, plus a `notifications/initialized` message.
Listing tools end to end:

```bash
SID=$(curl -s -D- -o /dev/null -X POST $BASE/mcp \
  -H "Authorization: Bearer $BEARER" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}' \
  | sed -n 's/^[Mm]cp-[Ss]ession-[Ii]d: *//p' | tr -d '\r')

curl -s -o /dev/null -X POST $BASE/mcp \
  -H "Authorization: Bearer $BEARER" -H "Mcp-Session-Id: $SID" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# expect 6 tools
curl -s -X POST $BASE/mcp \
  -H "Authorization: Bearer $BEARER" -H "Mcp-Session-Id: $SID" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

# a real call, as the user
curl -s -X POST $BASE/mcp \
  -H "Authorization: Bearer $BEARER" -H "Mcp-Session-Id: $SID" \
  -H "x-geonode-access-token: $ACCESS" -H "x-geonode-refresh-token: $REFRESH" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_resources","arguments":{"query":"test"}}}'
```

---

## Troubleshooting

### `404` on `/mcp`

The proxy location is not in effect. Confirm it is in the *running* config, not
just the file you edited:

```bash
docker exec <nginx-container> grep -n "location /mcp" /etc/nginx/sites-enabled/*.conf
```

If it is missing while present in your image, check whether `/etc/nginx` is a
**named volume**. Docker seeds such a volume from the image only when it is
first created; after that it masks the image, and config from a newer image
never arrives. Remove the volume mount, or recreate the volume.

### `301` or `307` loop on `/mcp`

Your location has a trailing slash. Change `location /mcp/` to `location /mcp`
and reload. See step 3.

### `401` on every call, even with a bearer token

`MCP_BEARER_TOKEN` in the container does not match what the client sends.
Compare without printing the secret:

```bash
docker exec <mcp-container> printenv MCP_BEARER_TOKEN | md5sum
echo -n '<token from client config>' | md5sum
```

### `invalid_client`

`GEONODE_OAUTH_CLIENT_ID` does not match the registered application. This breaks
setup for everyone and silently breaks token refresh. Compare:

```bash
ENVID=$(docker exec <mcp-container> printenv GEONODE_OAUTH_CLIENT_ID)
DBID=$(docker exec <geonode-django-container> python3 manage.py shell -c "
from oauth2_provider.models import get_application_model as A
print(A().objects.get(name='geonode-mcp').client_id)" | tr -d '\r\n ')
[ "$ENVID" = "$DBID" ] && echo MATCH || echo MISMATCH
```

On `MISMATCH`, set the environment variable to the database value and restart.

### `invalid_grant`

The application exists but the credentials were rejected, or the grant type is
wrong. Confirm it is `public` + `password` (step 1), then confirm the user can
log in to GeoNode's web UI with the same credentials.

### "GeoNode access token missing"

The tool ran but got no user identity. The client is not sending
`x-geonode-access-token` / `x-geonode-refresh-token`. Recheck the client config
from step 4 - this error means layers 1 and 2 are both working correctly and
just the headers are absent.

### Tools worked, then stopped after a while

The access token expired and refresh failed. Two causes: the `client_id`
mismatch above, or the client discarded a `refreshed_tokens` payload and is now
holding a rotated-away refresh token. Re-run `geonode-mcp-setup` to recover,
then fix the underlying cause - otherwise it returns.

### `base_url must be https://`

Intentional. The password grant refuses to post credentials over plaintext HTTP.
Use HTTPS; do not work around it.
