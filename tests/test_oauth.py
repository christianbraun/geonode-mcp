# ABOUTTHIS: Password grant and refresh grant against a stubbed GeoNode /o/token/.
# ABOUTTHIS: No live GeoNode instance involved.
import httpx
import pytest
import respx

from geonode_mcp.oauth import OAuthError, password_grant, refresh_grant


@respx.mock
def test_password_grant_returns_token_pair():
    respx.post("https://geonode.example/o/token/").mock(
        return_value=httpx.Response(200, json={"access_token": "at-1", "refresh_token": "rt-1"})
    )
    with httpx.Client() as client:
        tokens = password_grant(
            client,
            base_url="https://geonode.example",
            client_id="cid",
            username="alice",
            password="hunter2",
        )
    assert tokens.access_token == "at-1"
    assert tokens.refresh_token == "rt-1"


@respx.mock
def test_password_grant_sends_credentials_as_form_data():
    route = respx.post("https://geonode.example/o/token/").mock(
        return_value=httpx.Response(200, json={"access_token": "at-1", "refresh_token": "rt-1"})
    )
    with httpx.Client() as client:
        password_grant(
            client,
            base_url="https://geonode.example",
            client_id="cid",
            username="alice",
            password="hunter2",
        )
    sent = route.calls[0].request.content.decode()
    assert "grant_type=password" in sent
    assert "username=alice" in sent
    assert "password=hunter2" in sent


@respx.mock
def test_password_grant_raises_on_rejection():
    respx.post("https://geonode.example/o/token/").mock(return_value=httpx.Response(400, text="invalid_grant"))
    with httpx.Client() as client, pytest.raises(OAuthError):
        password_grant(
            client,
            base_url="https://geonode.example",
            client_id="cid",
            username="alice",
            password="wrong",
        )


def test_password_grant_refuses_plaintext_http():
    with httpx.Client() as client, pytest.raises(OAuthError):
        password_grant(
            client,
            base_url="http://geonode.example",
            client_id="cid",
            username="alice",
            password="hunter2",
        )


@respx.mock
def test_refresh_grant_returns_new_token_pair():
    respx.post("https://geonode.example/o/token/").mock(
        return_value=httpx.Response(200, json={"access_token": "at-2", "refresh_token": "rt-2"})
    )
    with httpx.Client() as client:
        tokens = refresh_grant(
            client,
            base_url="https://geonode.example",
            client_id="cid",
            refresh_token="rt-1",
        )
    assert tokens.access_token == "at-2"
    assert tokens.refresh_token == "rt-2"
