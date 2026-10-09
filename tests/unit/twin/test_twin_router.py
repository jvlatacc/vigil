"""Route-level tests for ``GET /api/twin/graph``.

The derivation itself is covered by ``test_graph.py``; here it is the wiring:
the response envelope, the auth gate (mounted like ``main.py`` mounts every
``Auth.REQUIRED`` router), and what the ``apply_exclusions`` query flag does
to the map.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from core.routing import request_unit_of_work
from core.twin.twin_router import router as twin_router
from services.api.middleware.auth import get_current_active_user

pytestmark = pytest.mark.unit

EXCLUDED_IP = "203.0.113.9"

FINDINGS = [
    SimpleNamespace(
        finding_id="f-1",
        entity_context={"src_ip": EXCLUDED_IP, "hostnames": ["web-01"]},
        severity="critical",
    ),
    SimpleNamespace(
        finding_id="f-2",
        entity_context={"ip": EXCLUDED_IP},
        severity="low",
    ),
]
CASE_ROWS = [("f-1", "case-7")]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Two statements reach the handler's session: the findings columns and
    the case_findings M2M. Told apart by the table each one selects from."""

    def __init__(self, finding_rows, case_rows):
        self._finding_rows = finding_rows
        self._case_rows = case_rows

    def execute(self, stmt):
        if "case_findings" in str(stmt):
            return _FakeResult(self._case_rows)
        return _FakeResult(self._finding_rows)


@pytest.fixture()
def app(authenticate_app):
    application = FastAPI()
    authenticate_app(application)
    application.include_router(twin_router, prefix="/api/twin")
    return application


def _override_session(app):
    app.dependency_overrides[request_unit_of_work] = lambda: _FakeSession(
        FINDINGS, CASE_ROWS
    )


def test_graph_response_shape(app, monkeypatch):
    _override_session(app)
    monkeypatch.setattr(
        "core.twin.twin_router.current_active_ips",
        lambda: frozenset({EXCLUDED_IP}),
    )

    body = TestClient(app).get("/api/twin/graph").json()

    assert set(body) == {
        "generated_at",
        "nodes",
        "edges",
        "unattributed_finding_ids",
    }
    ids = [node["id"] for node in body["nodes"]]
    assert ids == ["host:web-01", "unattributed"]
    host = body["nodes"][0]
    assert set(host) == {
        "id",
        "kind",
        "label",
        "finding_ids",
        "case_ids",
        "severity_counts",
        "x",
        "y",
    }
    assert host["kind"] == "host"
    assert host["finding_ids"] == ["f-1"]
    assert host["case_ids"] == ["case-7"]
    assert isinstance(host["x"], float) and isinstance(host["y"], float)
    assert body["unattributed_finding_ids"] == ["f-2"]


def test_excluded_ips_are_off_the_map_by_default(app, monkeypatch):
    _override_session(app)
    active = []

    def fake_active():
        active.append(1)
        return frozenset({EXCLUDED_IP})

    monkeypatch.setattr(
        "core.twin.twin_router.current_active_ips", fake_active
    )

    body = TestClient(app).get("/api/twin/graph").json()

    assert "ip:203.0.113.9" not in [node["id"] for node in body["nodes"]]
    assert active == [1]


def test_apply_exclusions_false_keeps_excluded_ips_and_skips_the_read(
    app, monkeypatch
):
    _override_session(app)

    def fail_if_read():
        raise AssertionError("apply_exclusions=false must not read exclusions")

    monkeypatch.setattr(
        "core.twin.twin_router.current_active_ips", fail_if_read
    )

    body = TestClient(app).get("/api/twin/graph?apply_exclusions=false").json()

    assert "ip:203.0.113.9" in [node["id"] for node in body["nodes"]]
    assert body["unattributed_finding_ids"] == []


def test_graph_requires_auth(monkeypatch):
    # Mounted the way services/api/main.py mounts every Auth.REQUIRED router:
    # the shared active-user dependency, and no authenticated user in place.
    # The session override keeps the dependency chain off the network; the
    # missing token must 401 before any query runs.
    bare = FastAPI()
    bare.include_router(
        twin_router, prefix="/api/twin", dependencies=[Depends(get_current_active_user)]
    )
    bare.dependency_overrides[request_unit_of_work] = lambda: _FakeSession([], [])

    response = TestClient(bare).get("/api/twin/graph")

    assert response.status_code == 401
