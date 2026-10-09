"""TTL-expiry sweep against a real Postgres (external_service marker).

Exercises the full release path: an executed ``honey_route`` row whose
``session_ttl_seconds`` has passed is unrouted by the sweep and the
reversal recorded on the action; a failed unroute keeps the row eligible
so the next sweep retries. The cluster side is faked at the route
module's ``unroute`` seam — this test owns the datastore behavior, not
the Kubernetes behavior. Runs in the unit tree's DB-backed convention:
``throwaway_database`` provisions a fresh database from the POSTGRES_*
env, so a local run needs a reachable Postgres (the DB-backed CI job
provides one).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

import core.integrations.honey_router.route as hr_module
from core.integrations.honey_router.route import sweep_expired_routes
from core.response.approval_service import (
    ActionStatus,
    ActionType,
    ApprovalService,
    Reversibility,
)
from core.time import utcnow

pytestmark = pytest.mark.external_service


@pytest.fixture(autouse=True)
def _throwaway_db(throwaway_database):
    """Every test here runs against the session's throwaway database."""
    assert throwaway_database


# The throwaway database is session-scoped, so rows a neighbour left would
# answer for this test: the sweep reads every executed honey_route row and
# the idempotency keys repeat across tests.
@pytest.fixture(autouse=True)
def _clean_routes(throwaway_database):
    from core.storage.connection import get_db_manager
    from core.storage.models.workflow import ApprovalAction

    with get_db_manager().session_scope() as session:
        session.query(ApprovalAction).filter(
            ApprovalAction.action_type == "honey_route"
        ).delete()
    yield


def _create_executed_route(svc: ApprovalService, ttl_seconds=3600, ip="203.0.113.7"):
    action = svc.create_action(
        action_type=ActionType.HONEY_ROUTE,
        title=f"honey_route: {ip}",
        description="test",
        target=ip,
        confidence=0.9,
        reason="test",
        evidence=["ev-1"],
        created_by="auto_responder",
        parameters={
            "decoy_id": "decoy-ssh-01",
            "session_ttl_seconds": ttl_seconds,
        },
        reversibility=Reversibility.REVERSIBLE,
        idempotency_key=f"honey_route:{ip}",
    )
    assert action.status == ActionStatus.APPROVED.value
    marked = svc.mark_executed(action.action_id, {"success": True, "backend": "cilium"})
    assert marked is not None and marked.status == ActionStatus.EXECUTED.value
    return action


def _fake_unroute(monkeypatch, results):
    """Replace the cluster unroute with a queued-results recorder."""
    calls = []

    def fake_unroute(attacker_ip):
        calls.append(attacker_ip)
        result = results.pop(0) if results else {"success": True}
        return {"policy": hr_module.policy_name_for(attacker_ip), **result}

    monkeypatch.setattr(hr_module, "unroute", fake_unroute)
    return calls


def _sweep(hours_ahead=2.0):
    return asyncio.run(
        sweep_expired_routes(now=utcnow() + timedelta(hours=hours_ahead))
    )


def _executed_honey_routes(svc):
    return svc.list_actions(
        status=ActionStatus.EXECUTED, action_type=ActionType.HONEY_ROUTE
    )


class TestTtlExpirySweep:
    def test_expired_route_is_unrouted_and_reversal_recorded(self, monkeypatch):
        svc = ApprovalService()
        action = _create_executed_route(svc, ttl_seconds=3600)
        calls = _fake_unroute(monkeypatch, [{"success": True}])

        result = _sweep()

        assert calls == ["203.0.113.7"]
        assert result["unrouted"] == 1
        assert result["failed"] == 0
        row = next(
            a for a in _executed_honey_routes(svc) if a.action_id == action.action_id
        )
        reversal = row.execution_result["reversal"]
        assert reversal["success"] is True
        assert reversal["reason"] == "ttl_expired"
        assert reversal["policy"].startswith("vigil-honey-")

    def test_not_yet_expired_route_is_left_alone(self, monkeypatch):
        svc = ApprovalService()
        _create_executed_route(svc, ttl_seconds=3600)
        calls = _fake_unroute(monkeypatch, [{"success": True}])

        result = _sweep(hours_ahead=0)  # now: TTL has not passed

        assert calls == []
        assert result["expired"] == 0

    def test_failed_unroute_is_recorded_and_retried_next_sweep(self, monkeypatch):
        svc = ApprovalService()
        action = _create_executed_route(svc, ttl_seconds=3600)
        _fake_unroute(monkeypatch, [{"success": False, "error": "cilium_api_error"}])

        first = _sweep()
        assert first["unrouted"] == 0
        assert first["failed"] == 1

        # The failed reversal is recorded, not forgotten — the sweep retries.
        row = next(
            a for a in _executed_honey_routes(svc) if a.action_id == action.action_id
        )
        assert row.execution_result["reversal"]["success"] is False
        assert row.execution_result["reversal"]["attempts"] == 1

        # One result per sweep: the retry sweep gets the success.
        _fake_unroute(monkeypatch, [{"success": True}])
        second = _sweep()
        assert second["unrouted"] == 1
        row = next(
            a for a in _executed_honey_routes(svc) if a.action_id == action.action_id
        )
        assert row.execution_result["reversal"]["success"] is True
        assert row.execution_result["reversal"]["attempts"] == 2

    def test_route_without_ttl_data_is_never_touched(self, monkeypatch):
        # A row missing TTL data must not be released on a guess.
        svc = ApprovalService()
        action = svc.create_action(
            action_type=ActionType.HONEY_ROUTE,
            title="honey_route: 203.0.113.8",
            description="test",
            target="203.0.113.8",
            confidence=0.9,
            reason="test",
            evidence=["ev-1"],
            created_by="auto_responder",
            parameters={"decoy_id": "decoy-ssh-01"},  # no session_ttl_seconds
            reversibility=Reversibility.REVERSIBLE,
            idempotency_key="honey_route:203.0.113.8",
        )
        svc.mark_executed(action.action_id, {"success": True, "backend": "cilium"})
        calls = _fake_unroute(monkeypatch, [])

        result = _sweep()

        assert calls == []
        assert result["expired"] == 0
