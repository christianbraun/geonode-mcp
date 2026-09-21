# ABOUTTHIS: Reads/writes the user's local GeoNode OAuth2 token pair on disk.
# ABOUTTHIS: Only access_token/refresh_token ever pass through here -- no LDAP password.
from __future__ import annotations

import json
from pathlib import Path

from geonode_mcp.oauth import TokenPair

DEFAULT_TOKEN_PATH = Path.home() / ".geonode-mcp" / "tokens.json"


def save(tokens: TokenPair, path: Path = DEFAULT_TOKEN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"access_token": tokens.access_token, "refresh_token": tokens.refresh_token}))
    path.chmod(0o600)


def load(path: Path = DEFAULT_TOKEN_PATH) -> TokenPair:
    data = json.loads(path.read_text())
    return TokenPair(access_token=data["access_token"], refresh_token=data["refresh_token"])
