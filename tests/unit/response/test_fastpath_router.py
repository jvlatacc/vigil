"""The fast-path console router: list and release.

Exercises both endpoints against the throwaway database through a bare
app with the same dependencies the real app wires: a request-scoped unit
of work for the list, and a rollback service sharing one recording
adapter for the release. The permission gate is deliberately left to the
security suites (``tests/security/test_route_permissions.py`` names the
release endpoint; ``test_unauth_endpoints.py`` refuses it unauthenticated)
— these tests answer "does the route do the right thing", not "who may".
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.deps import provide_rollback
from core.response import fastpath_router
from core.response.approval_service import (
    ActionStatus,
    ActionType,
    ApprovalService,
)
from core.response.config import ResponseConfig
from core.response.fastpath.adapters import EnforcementRegistry, EnforceResult
from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.policy import FastPathDecision
from core.response.fastpath.rollback import (
    RELEASE_REASON_HUMAN,
    RollbackService,
)
from core.response.fastpath.speculative_service import SpeculativeActionService
from core.routing import request_unit_of_work
from core.storage.models import ApprovalAction
from core.storage.unit_of_work import unit_of_work

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]


@pytest.fixture(autouse=True)
def _leave_no_live_speculative_rows():
    """Resolve every speculative row this file leaves behind.

    Same discipline as the rollback suites: the throwaway database is
    session-scoped and the idempotency keys here collide across tests.
    """
    yield
    with unit_of_work() as session:
        session.query(ApprovalAction).filter(
            ApprovalAction.status == ActionStatus.SPECULATIVE.value
        ).update({ApprovalAction.status: ActionStatus.ROLLED_BACK.value})


def _target(n: int) -> str:
    return f"203.0.113.{n}"


class _RecordingAdapter:
    """Counts apply and release calls; never touches a network."""

    simulates = False
    name = "recording"

    def __init__(self, fail_release: bool = False):
        self.applies: list = []
        self.releases: list = []
        self.fail_release = fail_release

    def applies_to(self):
        return frozenset({"rate_limit", "tarpit", "session_pin", "latency_inject"})

    def apply(self, action):
        self.applies.append(action.action_id)
        return EnforceResult(True, "rs-1:rule-1", "enforced")

    def release(self, action):
        self.releases.append(action.action_id)
        if self.fail_release:
            return EnforceResult(False, None, "vendor unreachable")
        return EnforceResult(True, None, "released")


class _SimulatingAdapter(_RecordingAdapter):
    simulates = True
    name = "simulating"


def _config(**overrides) -> FastPathConfig:
    return FastPathConfig(enabled=True, **overrides)


def _decision(target: str, **overrides) -> FastPathDecision:
    values: dict[str, Any] = dict(
        action_type="rate_limit",
        target=target,
        ttl_seconds=600,
        rule="fast_path.review_threshold=0.85 met (0.92)",
        signals={
            "tier": "t1",
            "finding_id": f"f-{target}",
            "severity": "critical",
            "confidence": 0.92,
        },
    )
    values.update(overrides)
    return FastPathDecision(**values)


def _pair(adapter, config=None):
    """A speculative service and a rollback service sharing one adapter."""
    cfg = config or _config()
    registry = EnforcementRegistry(
        {action_type: adapter for action_type in cfg.allowed_action_types}
    )
    approvals = ApprovalService(config=ResponseConfig())
    return (
        SpeculativeActionService(config=cfg, approvals=approvals, registry=registry),
        RollbackService(config=cfg, approvals=approvals, registry=registry),
    )


def _make_speculative(target: str, adapter=None):
    speculative, rollback = _pair(adapter or _RecordingAdapter())
    outcome = speculative.create_speculative_action(_decision(target))
    assert outcome is not None and outcome.inserted
    return outcome.action.action_id, rollback


def _request_session():
    with unit_of_work() as session:
        yield session


def _client(rollback, authenticate_app) -> TestClient:
    app = FastAPI()
    app.include_router(
        fastpath_router.router, prefix=fastpath_router.ROUTER_META.prefix
    )
    app.dependency_overrides[request_unit_of_work] = _request_session
    app.dependency_overrides[provide_rollback] = lambda: rollback
    authenticate_app(app)
    return TestClient(app, raise_server_exceptions=False)


def _row(action_id: str) -> ApprovalAction:
    with unit_of_work() as session:
        row = session.get(ApprovalAction, action_id)
        assert row is not None
        session.expunge(row)
        return row


class TestList:
    def test_lists_fast_path_rows_with_their_lifecycle_fields(self, authenticate_app):
        action_id, rollback = _make_speculative(_target(41))

        response = _client(rollback, authenticate_app).get("/api/fast-path/actions")

        rows = response.json()["actions"]
        # The throwaway database is shared: scope to this test's own row.
        row = next(r for r in rows if r["action_id"] == action_id)
        assert row["status"] == "speculative"
        assert row["target"] == _target(41)
        assert row["expires_at"] is not None
        assert row["simulated"] is False
        assert row["reason"].startswith("fast_path.review_threshold")
        assert response.json()["counts"].get("speculative", 0) >= 1

    def test_a_simulated_row_is_labeled(self, authenticate_app):
        action_id, rollback = _make_speculative(_target(42), _SimulatingAdapter())

        response = _client(rollback, authenticate_app).get("/api/fast-path/actions")

        row = next(r for r in response.json()["actions"] if r["action_id"] == action_id)
        assert row["simulated"] is True

    def test_rows_nobody_else_created_are_not_the_fast_path_s(self, authenticate_app):
        _, rollback = _pair(_RecordingAdapter())
        # A plain pipeline row from another actor must not appear here: this
        # screen is the fast path's ledger slice, not a second approvals queue.
        analyst_action = ApprovalService(config=ResponseConfig()).create_action(
            action_type=ActionType.WAF_BLOCK,
            title="block it",
            description="analyst ask",
            target=_target(43),
            confidence=0.9,
            reason="analyst ask",
            evidence=[],
            created_by="analyst",
        )

        response = _client(rollback, authenticate_app).get("/api/fast-path/actions")

        listed = [r["action_id"] for r in response.json()["actions"]]
        assert analyst_action.action_id not in listed

    def test_status_filter_narrows_and_refuses_unknown_values(self, authenticate_app):
        action_id, rollback = _make_speculative(_target(44))
        client = _client(rollback, authenticate_app)
        released = client.post(f"/api/fast-path/actions/{action_id}/release")
        assert released.status_code == 200

        live = client.get("/api/fast-path/actions", params={"status": "speculative"})
        assert action_id not in [r["action_id"] for r in live.json()["actions"]]

        gone = client.get("/api/fast-path/actions", params={"status": "rolled_back"})
        assert action_id in [r["action_id"] for r in gone.json()["actions"]]

        bad = client.get("/api/fast-path/actions", params={"status": "vanished"})
        assert bad.status_code == 400


class TestRelease:
    def test_a_person_releases_a_live_row(self, authenticate_app):
        action_id, rollback = _make_speculative(_target(45))

        response = _client(rollback, authenticate_app).post(
            f"/api/fast-path/actions/{action_id}/release"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["released"] is True
        assert body["action"]["status"] == "rolled_back"
        row = _row(action_id)
        assert row.status == ActionStatus.ROLLED_BACK.value
        assert row.execution_result["reason"] == RELEASE_REASON_HUMAN
        # The record names the person, not the endpoint.
        assert row.execution_result["actor"] == "test-admin"
        assert RELEASE_REASON_HUMAN in (row.reason or "")

    def test_an_unknown_action_is_not_found(self, authenticate_app):
        _, rollback = _pair(_RecordingAdapter())

        response = _client(rollback, authenticate_app).post(
            "/api/fast-path/actions/fp-never-was/release"
        )

        assert response.status_code == 404

    def test_a_resolved_row_has_nothing_left_to_release(self, authenticate_app):
        action_id, rollback = _make_speculative(_target(46))
        client = _client(rollback, authenticate_app)
        assert (
            client.post(f"/api/fast-path/actions/{action_id}/release").status_code
            == 200
        )

        response = client.post(f"/api/fast-path/actions/{action_id}/release")

        assert response.status_code == 409
        assert "rolled_back" in response.json()["detail"]

    def test_an_adapter_refusal_leaves_the_restriction_live(self, authenticate_app):
        # The vendor cannot lift the restriction: saying "released" would
        # report a lifted rule that is still in force. 502, row untouched,
        # the sweep (and the next click) can retry.
        action_id, rollback = _make_speculative(
            _target(47), _RecordingAdapter(fail_release=True)
        )

        response = _client(rollback, authenticate_app).post(
            f"/api/fast-path/actions/{action_id}/release"
        )

        assert response.status_code == 502
        assert _row(action_id).status == ActionStatus.SPECULATIVE.value
