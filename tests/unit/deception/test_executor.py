"""AC5 — the executor arm: steer with the lease scope, record the rollback.

Runs against a fake lease registry and the real DryRunBackend — no database.
The registry's durable half is covered DB-backed in test_lease_lifecycle_db.py.
"""

from unittest.mock import MagicMock

import pytest

from tests.unit.deception.fixtures import ATTACKER, VICTIM

from core.deception.backends import DryRunBackend
from core.response.approval_service import PendingAction
from core.response.autonomous_response_service import AutonomousResponseService
from core.response.config import ResponseConfig

pytestmark = pytest.mark.unit

PARAMS = {
    "attacker_ip": ATTACKER,
    "destination_ips": [VICTIM],
    "ports": [445, 3389],
}


def _honey_row(action_id="h1", **overrides):
    row = PendingAction(
        action_id=action_id,
        action_type="honey_route",
        title="Honey Route",
        description="d",
        target=ATTACKER,
        confidence=0.85,
        reason="r",
        evidence=[],
        created_at="",
        created_by="responder",
        requires_approval=True,
        status="approved",
        approved_by="analyst",
        parameters=dict(PARAMS),
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


class _FakeLeaseService:
    """The registry surface _execute_honey_route uses, in memory."""

    def __init__(self, backend=None, existing=None):
        self.backend = backend or DryRunBackend()
        self.existing = existing
        self.minted = []
        self.steered = []

    def by_action(self, action_id):
        return self.existing

    def mint(self, **kwargs):
        lease_id = f"lease-{len(self.minted)}"
        self.minted.append(kwargs)
        return lease_id

    async def steer_lease(self, lease_id, ttl_seconds=None, now=None):
        self.steered.append((lease_id, ttl_seconds))
        return {"success": True, "backend": "dry_run", "backend_ref": f"dry-run:{lease_id}"}


class _FailingLeaseService(_FakeLeaseService):
    async def steer_lease(self, lease_id, ttl_seconds=None, now=None):
        return {"success": False, "error": "backend exploded"}


class _ApprovalSpy:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []
        self.failed = []

    def list_actions(self, status=None, **_):
        return list(self.rows)

    def mark_executed(self, action_id, result):
        self.executed.append((action_id, result))

    def mark_failed(self, action_id, error):
        self.failed.append((action_id, error))


def _service(rows) -> AutonomousResponseService:
    service = AutonomousResponseService.__new__(AutonomousResponseService)
    service.approval_service = _ApprovalSpy(rows)
    service.config = ResponseConfig(honey_route_enabled=True)
    return service


@pytest.fixture
def registry(monkeypatch):
    holder = {}

    def _install(fake):
        holder["fake"] = fake
        monkeypatch.setattr(
            "core.deception.leases.DeceptionLeaseService", lambda **_: fake
        )
        return fake

    return _install


class TestTheExecutorArm:
    def test_an_approved_honey_row_steers_and_records_the_rollback(self, registry):
        fake = registry(_FakeLeaseService())
        service = _service([_honey_row()])

        results = service.execute_approved_actions()

        assert len(results) == 1
        assert results[0]["result"]["success"] is True
        # The scope the backend received is the lease scope, port-scoped.
        assert fake.minted[0]["attacker_ip"] == ATTACKER
        assert fake.minted[0]["ports"] == [445, 3389]
        assert fake.steered[0] == ("lease-0", 3600)
        # execution_result carries the rollback record — the pipeline's first.
        (action_id, recorded) = service.approval_service.executed[0]
        assert action_id == "h1"
        assert recorded["lease_id"] == "lease-0"
        assert recorded["ttl"] == 3600
        assert recorded["rollback"] == "DELETE /steer/lease-0"
        assert recorded["backend"] == "dry_run"

    def test_a_backend_failure_marks_failed_and_touches_nothing(self, registry):
        fake = registry(_FailingLeaseService())
        service = _service([_honey_row()])

        results = service.execute_approved_actions()

        assert len(results) == 1
        assert results[0]["result"]["success"] is False
        assert service.approval_service.executed == []
        assert service.approval_service.failed == [("h1", "backend exploded")]

    def test_an_active_lease_is_reused_not_reminted(self, registry):
        class _Row:
            lease_id = "lease-alive"
            status = "active"

        fake = registry(_FakeLeaseService(existing=_Row()))
        service = _service([_honey_row()])

        service.execute_approved_actions()

        assert fake.minted == []  # the crashed attempt's lease is picked up
        (action_id, recorded) = service.approval_service.executed[0]
        assert recorded["lease_id"] == "lease-alive"

    def test_a_row_no_person_decided_is_not_executed(self, registry):
        registry(_FakeLeaseService())
        service = _service([_honey_row(requires_approval=False, approved_by=None)])

        results = service.execute_approved_actions()

        assert results == []
        assert service.approval_service.executed == []

    def test_the_sweep_reaches_honey_rows_among_the_others(self, registry):
        """The dispatch arm sits beside isolate and Cloudflare — one sweep."""
        fake = registry(_FakeLeaseService())
        cloudflare = _honey_row("c1", action_type="waf_block")
        service = _service([cloudflare, _honey_row("h1")])
        service._execute_cloudflare_action = MagicMock(return_value={"success": True})

        results = service.execute_approved_actions()

        assert [r["action_id"] for r in results] == ["c1", "h1"]
        service._execute_cloudflare_action.assert_called_once()
