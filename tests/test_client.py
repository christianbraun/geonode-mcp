# ABOUTTHIS: GeoNodeClient forwards the access token as Bearer, and on a 401
# ABOUTTHIS: transparently refreshes via GeoNode's stubbed /o/token/ and retries once.
import httpx
import respx

from geonode_mcp.client import GeoNodeClient
from geonode_mcp.oauth import TokenPair


@respx.mock
def test_request_attaches_bearer_token():
    route = respx.get("https://geonode.example/api/v2/resources").mock(return_value=httpx.Response(200, json={}))
    with httpx.Client() as http_client:
        client = GeoNodeClient(
            http_client,
            base_url="https://geonode.example",
            client_id="cid",
            tokens=TokenPair(access_token="at-1", refresh_token="rt-1"),
        )
        client.request("GET", "/api/v2/resources")
    assert route.calls[0].request.headers["Authorization"] == "Bearer at-1"


@respx.mock
def test_401_refreshes_and_retries_once():
    resources_route = respx.get("https://geonode.example/api/v2/resources").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"ok": True})]
    )
    respx.post("https://geonode.example/o/token/").mock(
        return_value=httpx.Response(200, json={"access_token": "at-2", "refresh_token": "rt-2"})
    )
    refreshed = []
    with httpx.Client() as http_client:
        client = GeoNodeClient(
            http_client,
            base_url="https://geonode.example",
            client_id="cid",
            tokens=TokenPair(access_token="at-1", refresh_token="rt-1"),
            on_token_refreshed=refreshed.append,
        )
        response = client.request("GET", "/api/v2/resources")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert resources_route.calls[1].request.headers["Authorization"] == "Bearer at-2"
    assert refreshed == [TokenPair(access_token="at-2", refresh_token="rt-2")]
    assert client.tokens.access_token == "at-2"
