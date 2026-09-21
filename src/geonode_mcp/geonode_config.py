# ABOUTTHIS: Server-wide GeoNode connection config (base URL, OAuth2 client_id)
# ABOUTTHIS: read from the environment -- not a per-user secret.
from __future__ import annotations

import os
from dataclasses import dataclass

GEONODE_BASE_URL_ENV = "GEONODE_BASE_URL"
GEONODE_OAUTH_CLIENT_ID_ENV = "GEONODE_OAUTH_CLIENT_ID"


class MissingGeoNodeConfigError(RuntimeError):
    """Raised when GEONODE_BASE_URL or GEONODE_OAUTH_CLIENT_ID is not set."""


@dataclass(frozen=True)
class GeoNodeConfig:
    base_url: str
    client_id: str


def geonode_config_from_env() -> GeoNodeConfig:
    base_url = os.environ.get(GEONODE_BASE_URL_ENV)
    client_id = os.environ.get(GEONODE_OAUTH_CLIENT_ID_ENV)
    if not base_url or not client_id:
        raise MissingGeoNodeConfigError(
            f"{GEONODE_BASE_URL_ENV} and {GEONODE_OAUTH_CLIENT_ID_ENV} must be set in the environment"
        )
    return GeoNodeConfig(base_url=base_url, client_id=client_id)
