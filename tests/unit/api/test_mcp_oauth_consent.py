"""The consent endpoints: the one interactive act an authorization-code server needs.

Start hands the UI an authorization URL (PKCE S256, RFC 8707 resource bound);
callback completes the exchange and stores the refresh token. Both are
integrations-admin routes, and both refuse servers the flow does not apply to.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.auth.auth_service import AuthService
from core.integrations.mcp import connection_state as cs
from core.integrations.mcp import oauth
from core.integrations.mcp.oauth import OAuthTokenProvider
from core.storage.models import User
from services.api.middleware.auth import get_current_active_user
from services.api.routers import mcp as mcp_api

pytestmark = pytest.mark.unit

AUTH_BLOCK = {
    "type": "oauth2",
    "grant": "authorization_code",
    "server_url": "https://sentinel.example.corp/mcp",
    "issuer_url": "https://idp.example",
    "client_id": "vigil-client",
    "scopes": ["read", "invoke"],
}

CLIENT_CREDENTIALS_BLOCK = {
    "type": "oauth2",
    "grant": "client_credentials",
    "server_url": "https://crowdstrike.example.corp/mcp",
    "issuer_url": "https://idp.example",
    "client_id": "vigil-cc",
    "client_secret_key": "MCP_CROWDSTRIKE_CLIENT_SECRET",
}

IDP_METADATA = {
    "authorization_endpoint": "https://idp.example/authorize",
    "token_endpoint": "https://idp.example/token",
}

TOKEN_DOC = {
    "access_token": "at-1",
    "refresh_token": "rt-1",
    "expires_in": 3600,
    "token_type": "Bearer",
}


@pytest.fixture(autouse=True)
def _fresh_registry():
    """One test, one token-provider registry."""
    oauth.reset_token_providers()
    yield
    oauth.reset_token_providers()


@pytest.fixture
def catalog(monkeypatch):
    """One OAuth code-grant server, one client-credentials server, one plain."""
    servers = {
        "sentinel": SimpleNamespace(name="sentinel", auth=dict(AUTH_BLOCK)),
        "crowdstrike": SimpleNamespace(
            name="crowdstrike", auth=dict(CLIENT_CREDENTIALS_BLOCK)
        ),
        "github": SimpleNamespace(name="github", auth=None),
    }
    monkeypatch.setattr(
        mcp_api.mcp_service, "list_servers", lambda: list(servers), raising=False
    )
    monkeypatch.setattr(
        mcp_api.mcp_service, "servers", servers, raising=False
    )
    monkeypatch.setattr(
        mcp_api.mcp_service, "is_server_enabled", lambda name: True, raising=False
    )
    return servers


@pytest.fixture
def store(monkeypatch):
    """The secrets store, faked in-process. The provider reads and writes
    ``MCP_OAUTH_REFRESH_SENTINEL`` here."""
    saved = {}

    def _set_secret(key, value):
        saved[key] = value
        return True

    monkeypatch.setattr(
        oauth, "get_secret", lambda key, default=None: saved.get(key, default)
    )
    monkeypatch.setattr(oauth, "set_secret", _set_secret)
    # The connection-state machine resolves secrets through its own import.
    monkeypatch.setattr(
        cs, "get_secret", lambda key, default=None: saved.get(key, default)
    )
    return saved


@pytest.fixture
def admin():
    user = User(username="ops", user_id="u-ops-1", role_id="role-admin", is_active=True)
    return user


@pytest.fixture
def client(admin, monkeypatch):
    monkeypatch.setattr(
        AuthService, "check_permission", staticmethod(lambda *args, **kwargs: True)
    )
    app = FastAPI()
    app.include_router(mcp_api.router, prefix="/api/mcp")
    app.dependency_overrides[get_current_active_user] = lambda: admin
    return TestClient(app)


def _mock_metadata(monkeypatch):
    monkeypatch.setattr(
        OAuthTokenProvider,
        "_authorization_server_metadata",
        AsyncMock(return_value=dict(IDP_METADATA)),
    )


def test_start_builds_a_pkce_and_resource_bound_authorization_url(
    client, catalog, store, monkeypatch
):
    _mock_metadata(monkeypatch)
    response = client.post("/api/mcp/oauth/sentinel/consent", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["authorization_url"].startswith("https://idp.example/authorize?")
    assert "code_challenge_method=S256" in body["authorization_url"]
    assert "resource=" in body["authorization_url"]
    assert body["state"]


def test_start_refuses_a_client_credentials_server(client, catalog, store):
    response = client.post("/api/mcp/oauth/crowdstrike/consent", json={})
    assert response.status_code == 409
    assert "client-credentials" in response.json()["detail"]


def test_start_refuses_a_server_without_an_auth_block(client, catalog, store):
    response = client.post("/api/mcp/oauth/github/consent", json={})
    assert response.status_code == 409


def test_start_refuses_an_unknown_server(client, catalog, store):
    response = client.post("/api/mcp/oauth/nonesuch/consent", json={})
    assert response.status_code == 404


def test_start_refuses_a_non_admin(client, catalog, store, monkeypatch):
    monkeypatch.setattr(
        AuthService, "check_permission", staticmethod(lambda *args, **kwargs: False)
    )
    response = client.post("/api/mcp/oauth/sentinel/consent", json={})
    assert response.status_code == 403


def test_callback_completes_consent_and_stores_the_refresh_token(
    client, catalog, store, monkeypatch
):
    _mock_metadata(monkeypatch)
    token_request = AsyncMock(return_value=dict(TOKEN_DOC))
    monkeypatch.setattr(OAuthTokenProvider, "_token_request", token_request)

    started = client.post("/api/mcp/oauth/sentinel/consent", json={}).json()
    response = client.post(
        "/api/mcp/oauth/sentinel/callback",
        json={"code": "the-code", "state": started["state"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["connection_state"] == "connected"
    assert body["client_id"] == "vigil-client"
    token_request.assert_awaited_once()
    form = token_request.await_args.args[0]
    assert form["code"] == "the-code"
    assert form["code_verifier"]  # the PKCE verifier rode the exchange
    assert store["MCP_OAUTH_REFRESH_SENTINEL"] == "rt-1"


def test_callback_with_a_state_that_does_not_match_is_refused(
    client, catalog, store, monkeypatch
):
    _mock_metadata(monkeypatch)
    monkeypatch.setattr(
        OAuthTokenProvider,
        "_token_request",
        AsyncMock(return_value=dict(TOKEN_DOC)),
    )
    client.post("/api/mcp/oauth/sentinel/consent", json={})

    response = client.post(
        "/api/mcp/oauth/sentinel/callback",
        json={"code": "the-code", "state": "forged"},
    )

    assert response.status_code == 400
    assert "state mismatch" in response.json()["detail"]
    assert "MCP_OAUTH_REFRESH_SENTINEL" not in store


def test_callback_without_a_started_consent_is_refused(client, catalog, store):
    response = client.post(
        "/api/mcp/oauth/sentinel/callback",
        json={"code": "the-code", "state": "whatever"},
    )
    assert response.status_code == 409


def test_callback_refuses_a_server_without_an_auth_block(client, catalog, store):
    response = client.post(
        "/api/mcp/oauth/github/callback",
        json={"code": "the-code", "state": "whatever"},
    )
    assert response.status_code == 409


def test_callback_refuses_a_non_admin(client, catalog, store, monkeypatch):
    monkeypatch.setattr(
        AuthService, "check_permission", staticmethod(lambda *args, **kwargs: False)
    )
    response = client.post(
        "/api/mcp/oauth/sentinel/callback",
        json={"code": "the-code", "state": "whatever"},
    )
    assert response.status_code == 403
