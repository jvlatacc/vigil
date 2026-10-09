"""The tool layer answers the caller's grant; admins can retire any credential.

E4, pinned against the real role model on SQLite -- no permission is mocked
and no test touches the network:

- A case-writing tool reached over MCP checks ``cases.write`` against the
  person the credential is bound to -- the same question the cases API asks
  its routes with (``permission_gate("cases.write")``). The caller without
  it is refused before any case service runs; the caller with it writes; a
  hunt (no bound principal) writes as before.
- An administrator lists every user's credentials and revokes any of them,
  leaving a ConfigAuditLog row naming who pulled it. A non-admin gets 403
  on both routes.
- Tokens stay hashed at rest; the list never carries a token or its hash.

The refusal and admin-revoke tests fail on pre-fix code: the old tool layer
had no permission check at all, and the old revoke route could not see
another user's credential.
"""

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.auth import mcp_credential_service as credentials
from core.auth.mcp_credential_service import authenticate
from core.cases.case_ioc_service import CaseIOCService
from core.cases.case_workflow_service import CaseWorkflowService
from core.integrations.mcp.surface import acting_as
from core.storage.models import ConfigAuditLog, McpCredential, Role, User
from core.storage.models.base import Base
from tools.mcp import vigil


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


def _analyst():
    return User(
        user_id="u-analyst",
        username="j.doe",
        email="j.doe@example.com",
        password_hash="",
        full_name="J. Doe",
        role_id="r-analyst",
        is_active=True,
        mfa_enabled=False,
    )


def _admin():
    return User(
        user_id="u-admin",
        username="ops-lead",
        email="ops@example.com",
        password_hash="",
        full_name="Ops Lead",
        role_id="r-admin",
        is_active=True,
        mfa_enabled=False,
    )


@pytest.fixture
def store():
    """Roles, users, and the session seam every real check resolves through.

    ``username_has_permission``, ``AuthService.check_permission`` and the
    credential service all open ``unit_of_work``; redirecting its session
    factory to this store points them at the real role model -- roles here
    are what a deployment would grant -- with no database at all.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Role.__table__,
            User.__table__,
            McpCredential.__table__,
            ConfigAuditLog.__table__,
        ],
    )
    maker = sessionmaker(bind=engine)
    session = maker()
    session.add(
        Role(
            role_id="r-admin",
            name="admin",
            description="",
            permissions={
                "integrations.write": True,
                "cases.write": True,
                "cases.read": True,
            },
        )
    )
    session.add(
        Role(
            role_id="r-analyst",
            name="analyst",
            description="",
            permissions={"cases.read": True},
        )
    )
    session.add(_admin())
    session.add(_analyst())
    session.commit()

    with patch("core.storage.unit_of_work.get_db_session", maker):
        yield maker

    session.close()


@pytest.fixture
def api():
    """The full FastAPI app with credentials routes mounted, no lifespan."""
    from services.api import main as backend_main
    from services.api.middleware import auth as auth_module

    client = TestClient(backend_main.app)
    client.auth_module = auth_module
    yield client
    backend_main.app.dependency_overrides.clear()


def _sign_in(api, user):
    """Bind the API's auth dependencies to a chosen principal."""
    app = api.app
    auth_module = api.auth_module
    app.dependency_overrides[auth_module.get_current_active_user] = lambda: user
    app.dependency_overrides[auth_module.get_current_user] = lambda: user


@contextmanager
def _service_session():
    yield object()


def _credential_id(store):
    """The one minted credential's id, read fresh -- mint's session is closed."""
    with store() as session:
        return session.query(McpCredential.credential_id).scalar()


class TestToolLayer:
    def _closed(self, recorded):
        """A close_case stub the closure schema accepts, recording the case id."""

        def _close(self, session, case_id, **kwargs):
            recorded.append(case_id)
            return {
                "case_id": case_id,
                "closure_category": kwargs.get("closure_category"),
                "closed_by": kwargs.get("closed_by"),
            }

        return _close

    def test_a_caller_whose_role_lacks_cases_write_is_refused(self, store):
        gateway = MagicMock()
        with patch("core.agents.tool_registry._data", return_value=gateway):
            with acting_as("j.doe"):
                out = json.loads(vigil.create_case(title="nope"))

        assert "error" in out
        assert "cases.write" in out["error"]
        assert not gateway.create_case.called

    def test_a_refused_caller_cannot_reach_close_case(self, store, monkeypatch):
        recorded = []
        monkeypatch.setattr(CaseWorkflowService, "close_case", self._closed(recorded))
        monkeypatch.setattr(vigil, "_service_session", _service_session)
        monkeypatch.setattr(vigil, "add_case_activity", lambda *a, **k: None)

        with acting_as("j.doe"):
            out = json.loads(
                vigil.close_case(case_id="case-9", closure_category="resolved")
            )

        assert "error" in out
        assert recorded == []

    def test_a_refused_caller_cannot_reach_the_ioc_service(self, store, monkeypatch):
        add_ioc = MagicMock()
        monkeypatch.setattr(CaseIOCService, "add_ioc", add_ioc)

        with acting_as("j.doe"):
            out = json.loads(
                vigil.add_case_ioc(case_id="case-9", ioc_type="ip", value="10.0.0.1")
            )

        assert "error" in out
        assert not add_ioc.called

    def test_a_caller_holding_cases_write_creates_a_case(self, store):
        gateway = MagicMock()
        gateway.create_case.return_value = {"case_id": "case-x", "title": "legit"}
        with patch("core.agents.tool_registry._data", return_value=gateway):
            with acting_as("ops-lead"):
                out = json.loads(vigil.create_case(title="legit"))

        assert out["case_id"] == "case-x"
        assert gateway.create_case.called

    def test_a_caller_holding_cases_write_closes_a_case(self, store, monkeypatch):
        recorded = []
        monkeypatch.setattr(CaseWorkflowService, "close_case", self._closed(recorded))
        monkeypatch.setattr(vigil, "_service_session", _service_session)
        monkeypatch.setattr(vigil, "add_case_activity", lambda *a, **k: None)

        with acting_as("ops-lead"):
            out = json.loads(
                vigil.close_case(case_id="case-9", closure_category="resolved")
            )

        assert recorded == ["case-9"]
        assert "error" not in out

    def test_a_hunt_with_no_principal_writes_as_before(self, store):
        gateway = MagicMock()
        gateway.create_case.return_value = {"case_id": "case-y"}
        with patch("core.agents.tool_registry._data", return_value=gateway):
            out = json.loads(vigil.create_case(title="from a hunt"))

        assert out["case_id"] == "case-y"


class TestCredentialLifecycle:
    def test_a_non_admin_is_refused_on_both_credential_routes(self, store, api):
        _sign_in(api, _analyst())

        listed = api.get("/api/mcp/surface/credentials")
        revoked = api.delete("/api/mcp/surface/credentials/mcp-some-id")

        assert listed.status_code == 403, listed.text
        assert revoked.status_code == 403, revoked.text

    def test_an_admin_lists_every_user_s_credentials(self, store, api):
        minted = credentials.mint("u-analyst", "laptop")
        credential_id = _credential_id(store)
        _sign_in(api, _admin())

        response = api.get("/api/mcp/surface/credentials")

        assert response.status_code == 200, response.text
        rows = response.json()["credentials"]
        mine = next(r for r in rows if r["credential_id"] == credential_id)
        assert mine["username"] == "j.doe"
        assert mine["label"] == "laptop"
        assert "token" not in mine
        assert "token_hash" not in mine
        assert minted.token not in response.text

    def test_an_admin_revokes_another_user_s_credential_and_leaves_an_audit_row(
        self, store, api
    ):
        minted = credentials.mint("u-analyst", "laptop")
        credential_id = _credential_id(store)
        _sign_in(api, _admin())

        response = api.delete(f"/api/mcp/surface/credentials/{credential_id}")

        assert response.status_code == 200, response.text
        assert response.json() == {"revoked": credential_id}
        assert authenticate(minted.token) is None

        with store() as session:
            row = (
                session.query(ConfigAuditLog)
                .filter_by(config_type="mcp_credential")
                .one()
            )
            assert row.config_key == credential_id
            assert row.action == "update"
            assert row.changed_by == "u-admin"
            assert row.old_value["user_id"] == "u-analyst"
            assert row.new_value == {"revoked": True}

    def test_an_admin_can_still_retire_their_own_credential(self, store, api):
        minted = credentials.mint("u-admin", "ops laptop")
        credential_id = _credential_id(store)
        _sign_in(api, _admin())

        response = api.delete(f"/api/mcp/surface/credentials/{credential_id}")

        assert response.status_code == 200, response.text
        assert authenticate(minted.token) is None

    def test_revoking_an_unknown_credential_is_a_404(self, store, api):
        _sign_in(api, _admin())

        response = api.delete("/api/mcp/surface/credentials/mcp-never-was")

        assert response.status_code == 404, response.text

    def test_revoking_twice_conflicts(self, store, api):
        credentials.mint("u-analyst", "laptop")
        credential_id = _credential_id(store)
        _sign_in(api, _admin())

        first = api.delete(f"/api/mcp/surface/credentials/{credential_id}")
        second = api.delete(f"/api/mcp/surface/credentials/{credential_id}")

        assert first.status_code == 200, first.text
        assert second.status_code == 409, second.text

    def test_a_non_admin_revocation_leaves_no_audit_row(self, store, api):
        credentials.mint("u-analyst", "laptop")
        credential_id = _credential_id(store)
        _sign_in(api, _analyst())

        response = api.delete(f"/api/mcp/surface/credentials/{credential_id}")

        assert response.status_code == 403, response.text
        with store() as session:
            assert session.query(ConfigAuditLog).count() == 0
