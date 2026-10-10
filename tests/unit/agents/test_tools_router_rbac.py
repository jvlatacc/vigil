"""Tool execution answers to the caller's role, and every call leaves a row.

The invoke boundary is where a verified username, a tool id and the arguments
coexist -- so it is where a person's standing is checked (the ``tools.execute``
baseline, or the per-server ``tools.server.<name>`` override) and where the
audit row is written. Both decisions land in the same store: a refusal nobody
can account for is not an enforcement decision, and a success nobody can
account for is not a success.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from core.agents import internal_auth, tool_registry, tools_router
from core.audit import tool_calls
from core.auth import tool_principal
from core.integrations.mcp.registry import MCPRegistry
from core.storage.models import ToolCallAudit

from tests.unit.agents.test_tools_router import _ground_audit_and_permission_store

BOUNDS = {"max_rows": 5, "timeout_ms": 5000}
AUTH = {"Authorization": "Bearer shhh"}

pytestmark = pytest.mark.unit


@pytest.fixture
def store(monkeypatch):
    """A store with an analyst (granted) and a viewer (not)."""
    return _ground_audit_and_permission_store(
        monkeypatch,
        users=(
            ("rory", "u-rory", "r-yes"),
            ("vera", "u-vera", "r-no"),
        ),
    )


@pytest.fixture
def app(monkeypatch, store):
    monkeypatch.setattr(internal_auth, "get_secret", lambda name: "shhh")
    return FastAPI()


def _rows(store):
    store.expire_all()
    return list(
        store.execute(select(ToolCallAudit).order_by(ToolCallAudit.id)).scalars()
    )


def _invoke(
    app,
    tool="list_findings",
    args=None,
    principal=None,
    run_id=None,
    registry=None,
):
    app.state.mcp_registry = registry if registry is not None else MCPRegistry()
    app.include_router(tools_router.router, prefix=tools_router.ROUTER_META.prefix)
    client = TestClient(app, raise_server_exceptions=True)
    body: dict = {"tool": tool, "args": args or {}, "bounds": BOUNDS}
    if run_id is not None:
        body["run_id"] = run_id
    if principal is not None:
        body["principal"] = principal
    return client.post("/internal/tools/invoke", json=body, headers=AUTH)


class TestDenialAtTheBoundary:
    def test_a_caller_without_the_grant_is_refused_and_recorded(self, app, store):
        response = _invoke(app, principal=tool_principal.mint("vera"))

        assert response.status_code == 403
        rows = _rows(store)
        assert len(rows) == 1
        row = rows[0]
        assert row.actor_username == "vera"
        assert row.surface == tool_calls.SURFACE_AGENT
        assert row.decision == tool_calls.DECISION_DENY
        assert row.deny_reason == "permission"
        assert row.args_sha256 is not None
        assert row.outcome is None

    def test_the_refusal_names_the_server_the_tool_belongs_to(self, app, store):
        """A per-server key is scoped to one server, so the row says which."""
        # The registry's tool contract is the dict shape client.py caches
        # ({"name", "description", "inputSchema"}) — register_server scans
        # descriptions with tool.get(...), so objects don't survive registration.
        schema = {
            "name": "create_issue",
            "description": "open an issue",
            "inputSchema": {"type": "object", "properties": {}},
        }
        registry = MCPRegistry()
        registry.register_server("github", {}, [schema])

        response = _invoke(
            app,
            tool="github_create_issue",
            args={"title": "x"},
            principal=tool_principal.mint("vera"),
            registry=registry,
        )

        assert response.status_code == 403
        row = _rows(store)[0]
        assert row.server_name == "github"
        assert row.tool_name == "github_create_issue"


class TestAllowance:
    def test_a_caller_with_the_grant_runs_and_is_recorded(self, app, store):
        response = _invoke(
            app, principal=tool_principal.mint("rory"), run_id="run-77"
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True
        rows = _rows(store)
        assert len(rows) == 1
        row = rows[0]
        assert row.actor_username == "rory"
        assert row.decision == tool_calls.DECISION_ALLOW
        assert row.deny_reason is None
        assert row.outcome == "ok"
        assert row.duration_ms is not None
        assert row.run_id == "run-77"

    def test_a_call_with_no_person_behind_it_is_recorded_as_the_agents(
        self, app, store
    ):
        """A hunt has no role to check and keeps the access it had -- recorded."""
        response = _invoke(app)

        assert response.status_code == 200
        row = _rows(store)[0]
        assert row.actor_username == tool_calls.ACTOR_AGENT
        assert row.decision == tool_calls.DECISION_ALLOW
        assert row.run_id is None

    def test_a_failed_tool_still_records_its_outcome(self, app, store):
        async def broken(name, args, **kwargs):
            raise RuntimeError("downstream gone")

        original = tools_router.execute_backend_tool
        tools_router.execute_backend_tool = broken
        try:
            response = _invoke(app, principal=tool_principal.mint("rory"))
        finally:
            tools_router.execute_backend_tool = original

        assert response.status_code == 200
        assert response.json()["ok"] is False
        row = _rows(store)[0]
        assert row.decision == tool_calls.DECISION_ALLOW
        assert row.outcome == "error"


class TestFailClosed:
    def test_an_unreadable_registry_stops_the_call(self, app, store):
        """No server name, no permission key to check -- the call cannot run."""
        registry = MagicMock()
        registry.get_active_servers.side_effect = RuntimeError("registry down")

        with pytest.raises(RuntimeError):
            _invoke(app, registry=registry, principal=tool_principal.mint("vera"))
        assert _rows(store) == []

    def test_an_allow_whose_row_cannot_be_written_is_not_a_success(self, app):
        from core.audit import tool_calls as tc

        @contextmanager
        def _broken_store(_=None):
            raise RuntimeError("audit store down")
            yield  # pragma: no cover

        original = tc.unit_of_work
        tc.unit_of_work = _broken_store
        try:
            with pytest.raises(RuntimeError):
                _invoke(app, principal=tool_principal.mint("rory"))
        finally:
            tc.unit_of_work = original
