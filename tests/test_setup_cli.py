# ABOUTTHIS: Setup command exchanges username/password for tokens and persists
# ABOUTTHIS: only the token pair to disk -- the raw password must never land there.
import json

import httpx
import respx

from geonode_mcp.setup_cli import run_setup


@respx.mock
def test_setup_persists_only_tokens_not_password(tmp_path):
    respx.post("https://geonode.example/o/token/").mock(
        return_value=httpx.Response(200, json={"access_token": "at-1", "refresh_token": "rt-1"})
    )
    token_path = tmp_path / "tokens.json"

    run_setup("https://geonode.example", "cid", "alice", "hunter2", token_path=token_path)

    saved = json.loads(token_path.read_text())
    assert saved == {"access_token": "at-1", "refresh_token": "rt-1"}
    assert "hunter2" not in token_path.read_text()
