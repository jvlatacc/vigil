"""GET /api/mcp/servers/status reports MCPClient session state, not the catalog."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.deps import provide_mcp_client
from core.integrations.mcp import connection_state, oauth
from core.storage.models import OAuthConnection
from core.storage.unit_of_work import unit_of_work
from services.api.routers import mcp as mcp_api

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_provider_registry():
    """One test, one token-provider registry and one connection memory."""
    oauth.reset_token_providers()
    _forget_stored_connections()
    yield
    oauth.reset_token_providers()


def _forget_stored_connections():
    """Drop oauth_connections rows an earlier test in this process may have stored.

    The status row reads that table as display memory; a consent test's row for
    a same-named server would outlive its test and resurface here. Like the
    product's own read, a database that cannot answer degrades to live knowledge.
    """
    try:
        with unit_of_work() as session:
            session.query(OAuthConnection).delete()
    except Exception:  # noqa: BLE001 - no database in this run is a fine start
        pass


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(mcp_api.router, prefix="/api/mcp")
    return TestClient(app)


def _catalog():
    return patch.object(
        mcp_api.mcp_service,
        "list_servers",
        return_value=["github", "virustotal", "slack"],
    ), patch.object(
        mcp_api.mcp_service,
        "get_all_enabled_states",
        return_value={"github": True, "virustotal": True, "slack": False},
    )


def test_status_route_reads_the_stubbed_client(client):
    stub = SimpleNamespace(
        get_connection_status=lambda: {
            "github": True,
            "virustotal": False,
            "slack": False,
        },
        get_last_error=lambda name: {"virustotal": "connection refused"}.get(name),
        get_missing_credentials=lambda name: {"virustotal": ["VT_API_KEY"]}.get(name),
        retry_dormant_if_ready=AsyncMock(),
    )
    client.app.dependency_overrides[provide_mcp_client] = lambda: stub
    servers, enabled = _catalog()
    with servers, enabled:
        response = client.get("/api/mcp/servers/status")

    assert response.status_code == 200
    rows = {row["name"]: row for row in response.json()["statuses"]}
    assert rows["github"] == {"name": "github", "status": "running", "enabled": True}
    assert rows["virustotal"] == {
        "name": "virustotal",
        "status": "disconnected",
        "enabled": True,
        "missing_credentials": ["VT_API_KEY"],
        "error": "connection refused",
    }
    assert rows["slack"] == {
        "name": "slack",
        "status": "disconnected",
        "enabled": False,
    }
    stub.retry_dormant_if_ready.assert_not_called()


def test_status_route_reports_disconnected_when_the_client_is_missing(client):
    client.app.dependency_overrides[provide_mcp_client] = lambda: None
    servers, enabled = _catalog()
    with servers, enabled:
        response = client.get("/api/mcp/servers/status")

    assert response.status_code == 200
    rows = response.json()["statuses"]
    assert [row["status"] for row in rows] == ["disconnected"] * 3
    assert [row["enabled"] for row in rows] == [True, True, False]
    assert all("error" not in row and "missing_credentials" not in row for row in rows)


SENTINEL_AUTH = {
    "type": "oauth2",
    "grant": "authorization_code",
    "server_url": "https://sentinel.example.corp/mcp",
    "issuer_url": "https://idp.example",
    "client_id": "vigil-client",
}


def test_status_route_merges_connection_state_for_oauth_servers(
    client, monkeypatch
):
    """A server whose config declares an ``auth`` block reports the five-state
    connection machine beside its session status; plain servers do not."""
    monkeypatch.setattr(
        connection_state, "get_secret", lambda key, default=None: default
    )
    stub = SimpleNamespace(
        get_connection_status=lambda: {"sentinel": False, "github": True},
        get_last_error=lambda name: None,
        get_missing_credentials=lambda name: None,
        retry_dormant_if_ready=AsyncMock(),
    )
    client.app.dependency_overrides[provide_mcp_client] = lambda: stub
    with patch.object(
        mcp_api.mcp_service,
        "list_servers",
        return_value=["sentinel", "github"],
    ), patch.object(
        mcp_api.mcp_service,
        "get_all_enabled_states",
        return_value={"sentinel": True, "github": True},
    ), patch.object(
        mcp_api.mcp_service,
        "servers",
        {
            "sentinel": SimpleNamespace(name="sentinel", auth=dict(SENTINEL_AUTH)),
            "github": SimpleNamespace(name="github", auth=None),
        },
    ):
        response = client.get("/api/mcp/servers/status")

    assert response.status_code == 200
    rows = {row["name"]: row for row in response.json()["statuses"]}
    # A server with no auth block keeps the exact shape it always had.
    assert rows["github"] == {
        "name": "github",
        "status": "running",
        "enabled": True,
    }
    # The code-grant server has never consented in this process and holds no
    # refresh token: needs_consent, with its non-secret metadata.
    assert rows["sentinel"]["status"] == "disconnected"
    assert rows["sentinel"]["connection_state"] == "needs_consent"
    assert rows["sentinel"]["oauth"]["grant"] == "authorization_code"
    assert rows["sentinel"]["oauth"]["client_id"] == "vigil-client"
    assert rows["sentinel"]["oauth"]["resource"] == "https://sentinel.example.corp/mcp"
    assert "last_error" not in rows["sentinel"]
