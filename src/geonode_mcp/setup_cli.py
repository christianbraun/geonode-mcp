# ABOUTTHIS: One-time local setup command: exchanges the user's LDAP
# ABOUTTHIS: username/password for a GeoNode OAuth2 token pair, then discards the password.
from __future__ import annotations

import argparse
import getpass
from pathlib import Path

import httpx

from geonode_mcp import token_store
from geonode_mcp.oauth import password_grant


def run_setup(
    base_url: str,
    client_id: str,
    username: str,
    password: str,
    token_path: Path = token_store.DEFAULT_TOKEN_PATH,
) -> None:
    with httpx.Client() as http_client:
        tokens = password_grant(
            http_client,
            base_url=base_url,
            client_id=client_id,
            username=username,
            password=password,
        )
    token_store.save(tokens, token_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="One-time GeoNode OAuth2 setup for geonode-mcp")
    parser.add_argument("--base-url", required=True, help="GeoNode base URL, e.g. https://geonode.example.org")
    parser.add_argument("--client-id", required=True, help="OAuth2 Application client_id registered in GeoNode")
    parser.add_argument("--username", required=True, help="Your LDAP username")
    args = parser.parse_args()

    password = getpass.getpass("GeoNode password: ")
    run_setup(args.base_url, args.client_id, args.username, password)
    print(f"Tokens saved to {token_store.DEFAULT_TOKEN_PATH}")


if __name__ == "__main__":
    main()
