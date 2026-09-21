# ABOUTTHIS: Layer 1 auth -- a static shared secret gate in front of every MCP
# ABOUTTHIS: tool call, checked before any tool or GeoNode call is reached.
from __future__ import annotations

import hmac
import os

from fastmcp.server.auth.auth import AccessToken, TokenVerifier

MCP_BEARER_TOKEN_ENV = "MCP_BEARER_TOKEN"


class MissingBearerTokenError(RuntimeError):
    """Raised when MCP_BEARER_TOKEN is not set in the environment."""


class StaticBearerTokenVerifier(TokenVerifier):
    """Accepts only the exact token configured via MCP_BEARER_TOKEN."""

    def __init__(self, expected_token: str) -> None:
        super().__init__()
        self._expected_token = expected_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token, self._expected_token):
            return None
        return AccessToken(token=token, client_id="mcp-bearer", scopes=[])


def bearer_token_verifier_from_env() -> StaticBearerTokenVerifier:
    token = os.environ.get(MCP_BEARER_TOKEN_ENV)
    if not token:
        raise MissingBearerTokenError(f"{MCP_BEARER_TOKEN_ENV} must be set in the environment")
    return StaticBearerTokenVerifier(token)
