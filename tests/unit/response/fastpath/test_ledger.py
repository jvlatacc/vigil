"""Unit tests for the containment lease drivers — the orchestration that
decides WHEN effects are removed relative to ledger writes.

No database is needed and none is faked into reach: the drivers take the
ledger as a duck-typed collaborator, so the fake ledger below records the
ORDER of every call (und vs. mark) — undo-then-mark ordering is exactly
the sequence, and a fake is more honest about order than a database. The
CAS tests use the ``no_db`` seam from ``test_approval_workflow.py``: a
mocked db manager whose ``execute`` result carries a rowcount.
"""

from __future__ import annotations

import asyncio
import inspect
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from core.response.fastpath import ledger as ledger_module
from core.response.fastpath.ledger import (
    ACTOR_SWEEPER,
    REASON_APPLY_FAILED,
    REASON_APPLY_RETRY_FAILED,
    REASON_NO_EXECUTOR,
    REASON_TTL_EXPIRED_BEFORE_APPLY,
    TTL_EXPIRED,
    ContainmentLedger,
    LeaseIntent,
    LeaseView,
    issue_and_apply,
    lease_spec_of,
    reconcile_stale_intents,
    rollback_lease,
    sweep_expired,
)
from core.storage.models import ContainmentAction
from core.time import utcnow

# ----------------------------------------------------------------------
# Fakes — call order is the assertion surface
# ----------------------------------------------------------------------


class FakeLedger:
    """In-memory stand-in for ContainmentLedger; records call order."""

    def __init__(
        self,
        leases: Optional[Dict[str, LeaseView]] = None,
        *,
        inserted: bool = True,
        cas_result: Any = "transition",
    ) -> None:
        self.leases = leases or {}
        self.inserted = inserted
        self.cas_result = cas_result  # "transition" | None
        self.calls: List[tuple] = []
        self.expired: List[LeaseView] = []
        self.stale: List[LeaseView] = []

    def _transition(self, lease_id: str, to_status: str, actor: str, reason=None):
        self.calls.append(("mark", lease_id, to_status, actor, reason))
        if self.cas_result == "transition":
            from core.response.fastpath.ledger import Transition

            return Transition(
                lease_id=lease_id,
                from_status="?",
                to_status=to_status,
                actor=actor,
                evidence_version=None,
                reason=reason,
            )
        return None

    # -- reads ---------------------------------------------------------
    def get(self, lease_id: str):
        self.calls.append(("get", lease_id))
        return self.leases.get(lease_id)

    def list_expired(self, now, batch_size=100):
        self.calls.append(("list_expired", len(self.expired)))
        return list(self.expired)

    def list_stale_intents(self, apply_timeout_seconds, now, batch_size=100):
        self.calls.append(("list_stale", len(self.stale)))
        return list(self.stale)

    # -- writes --------------------------------------------------------
    def issue(self, intent: LeaseIntent):
        self.calls.append(("issue", intent.idempotency_key))
        lease = self.leases.get("issued") or _view(id="lease-new")
        return lease, self.inserted

    def mark_applied(self, lease_id, undo_payload, actor, evidence_version):
        self.calls.append(
            ("mark_applied", lease_id, dict(undo_payload or {}), evidence_version)
        )
        return self._transition(lease_id, "applied", actor)

    def mark_rolled_back(self, lease_id, reason, actor, evidence_version):
        self.calls.append(("mark_rolled_back", lease_id, reason, evidence_version))
        return self._transition(lease_id, "rolled_back", actor, reason)

    def mark_failed(self, lease_id, reason, actor, evidence_version):
        self.calls.append(("mark_failed", lease_id, reason, evidence_version))
        return self._transition(lease_id, "failed", actor, reason)


class RecordingExecutor:
    """Idempotent fake executor with programmable failures."""

    def __init__(self, *, apply_raises: bool = False, undo_raises: bool = False):
        self.apply_raises = apply_raises
        self.undo_raises = undo_raises
        self.undo_calls: List[tuple] = []
        self.apply_calls: List[Any] = []

    async def apply(self, lease) -> Dict[str, Any]:
        self.apply_calls.append(lease)
        if self.apply_raises:
            raise RuntimeError("apply exploded")
        return {"rule_id": "rule-1"}

    async def undo(self, lease_id: str, undo_payload: Dict[str, Any]) -> None:
        self.undo_calls.append((lease_id, dict(undo_payload or {})))
        if self.undo_raises:
            raise RuntimeError("undo exploded")


def _view(
    *,
    id: str = "lease-1",
    action_type: str = "challenge",
    status: str = "applied",
    expires_at: Optional[datetime] = None,
    undo_payload: Optional[Dict] = None,
    is_shadow: bool = False,
) -> LeaseView:
    return LeaseView(
        id=id,
        action_type=action_type,
        entity_type="ip",
        entity_id="203.0.113.7",
        status=status,
        idempotency_key=f"{action_type}:ip:203.0.113.7",
        finding_id="finding-1",
        decision_rule="severity >= high",
        observed={"severity": "critical", "confidence": 0.93},
        undo_payload=undo_payload if undo_payload is not None else {"rule_id": "r-1"},
        is_shadow=is_shadow,
        ttl_seconds=300,
        expires_at=expires_at or (utcnow() + timedelta(seconds=300)),
        created_at=utcnow(),
    )


def _intent(**overrides) -> LeaseIntent:
    fields = dict(
        action_type="challenge",
        entity_type="ip",
        entity_id="203.0.113.7",
        ttl_seconds=300,
        decision_rule="severity >= high",
        observed={"severity": "critical"},
    )
    fields.update(overrides)
    return LeaseIntent(**fields)


class FakeRegistry:
    def __init__(self, executor: Any = None):
        self._executor = executor

    def get(self, action_type: str):
        return self._executor


# ----------------------------------------------------------------------
# rollback_lease — undo-then-mark ordering
# ----------------------------------------------------------------------


class TestRollbackLease:
    async def test_undo_happens_before_the_row_closes(self):
        ledger = FakeLedger(leases={"lease-1": _view()})
        executor = RecordingExecutor()
        # One shared sequence for BOTH collaborators, so "undo completed
        # before the row closed" is an index comparison, not a vibe.
        original_undo = executor.undo

        async def spy_undo(lease_id: str, payload):
            ledger.calls.append(("EXECUTOR_UNDO", lease_id))
            return await original_undo(lease_id, payload)

        executor.undo = spy_undo

        await rollback_lease(ledger, executor, "lease-1", "downgraded")

        order = [c[0] for c in ledger.calls]
        assert order.index("EXECUTOR_UNDO") < order.index("mark_rolled_back")
        mark = next(c for c in ledger.calls if c[0] == "mark_rolled_back")
        assert mark[1] == "lease-1"
        assert mark[2] == "downgraded"

    async def test_unknown_lease_is_a_no_op(self):
        ledger = FakeLedger()  # no leases
        executor = RecordingExecutor()

        result = await rollback_lease(ledger, executor, "ghost", "downgraded")

        assert result is None
        assert executor.undo_calls == []
        assert not any(c[0].startswith("mark") for c in ledger.calls)

    async def test_non_live_lease_is_a_no_op(self):
        ledger = FakeLedger(leases={"lease-1": _view(status="pending_apply")})
        executor = RecordingExecutor()

        result = await rollback_lease(ledger, executor, "lease-1", "downgraded")

        assert result is None
        assert executor.undo_calls == []

    async def test_undo_failure_leaves_the_row_live_for_the_sweeper(self):
        ledger = FakeLedger(leases={"lease-1": _view()})
        executor = RecordingExecutor(undo_raises=True)

        with pytest.raises(RuntimeError, match="undo exploded"):
            await rollback_lease(ledger, executor, "lease-1", "downgraded")

        # The row never closed: a crash-with-undo-failure must NOT be
        # mistaken for a rollback — the sweep reconciles the still-live
        # lease, and the effect can never outlive its row.
        assert not any(c[0] == "mark_rolled_back" for c in ledger.calls)


# ----------------------------------------------------------------------
# issue_and_apply — write-behind, replay, shadow, CAS loser
# ----------------------------------------------------------------------


class TestIssueAndApply:
    async def test_replay_never_touches_the_executor(self):
        ledger = FakeLedger(inserted=False)
        executor = RecordingExecutor()

        outcome = await issue_and_apply(ledger, _intent(), executor)

        assert outcome.replay is True
        assert outcome.applied is False
        assert executor.apply_calls == []

    async def test_shadow_intent_records_without_applying(self):
        ledger = FakeLedger(inserted=True)
        # The ledger returns a shadow view for a fresh insert.
        ledger.leases["issued"] = _view(is_shadow=True)
        executor = RecordingExecutor()

        outcome = await issue_and_apply(ledger, _intent(is_shadow=True), executor)

        assert outcome.shadow is True
        assert outcome.applied is False
        assert executor.apply_calls == []

    async def test_happy_path_applies_then_marks(self):
        ledger = FakeLedger(inserted=True)
        ledger.leases["issued"] = _view(status="pending_apply")
        executor = RecordingExecutor()

        outcome = await issue_and_apply(ledger, _intent(), executor)

        assert outcome.applied is True
        mark = next(c for c in ledger.calls if c[0] == "mark_applied")
        assert mark[1] == "lease-1"  # the seeded view's id
        assert mark[2] == {"rule_id": "rule-1"}

    async def test_apply_failure_undoes_then_marks_failed(self):
        ledger = FakeLedger(inserted=True)
        ledger.leases["issued"] = _view(status="pending_apply")
        executor = RecordingExecutor(apply_raises=True)

        outcome = await issue_and_apply(ledger, _intent(), executor)

        assert outcome.applied is False
        assert outcome.error  # the apply exception surfaced on the outcome
        # Uncertainty undo ran BEFORE the row closed.
        assert executor.undo_calls == [("lease-1", {})]
        failed = next(c for c in ledger.calls if c[0] == "mark_failed")
        assert failed[1] == "lease-1"
        assert failed[2] == REASON_APPLY_FAILED

    async def test_apply_failure_where_undo_also_fails_still_marks_failed(self):
        """Neither failure may leak: the lease row must close so the
        idempotency key frees and the sweep owns the aftermath."""
        ledger = FakeLedger(inserted=True)
        ledger.leases["issued"] = _view(status="pending_apply")
        executor = RecordingExecutor(apply_raises=True, undo_raises=True)

        outcome = await issue_and_apply(ledger, _intent(), executor)

        assert outcome.applied is False
        failed = next(c for c in ledger.calls if c[0] == "mark_failed")
        assert failed[2] == REASON_APPLY_FAILED

    async def test_cas_loser_gets_a_compensating_undo(self):
        """The row moved while the apply was in flight — the reconciler
        aborted it, or adjudication closed it. The effect must not
        outlive the row."""
        ledger = FakeLedger(inserted=True, cas_result=None)
        ledger.leases["issued"] = _view(status="pending_apply")
        executor = RecordingExecutor()

        outcome = await issue_and_apply(ledger, _intent(), executor)

        assert outcome.applied is False
        # The very same undo payload the apply just produced.
        assert executor.undo_calls == [("lease-1", {"rule_id": "rule-1"})]

    async def test_evidence_version_rides_the_transition(self):
        ledger = FakeLedger(inserted=True)
        ledger.leases["issued"] = _view(status="pending_apply")
        executor = RecordingExecutor()

        await issue_and_apply(ledger, _intent(), executor, evidence_version="ev-42")

        mark = next(c for c in ledger.calls if c[0] == "mark_applied")
        assert mark[3] == "ev-42"


# ----------------------------------------------------------------------
# sweep_expired — datastore-enforced expiry
# ----------------------------------------------------------------------


class TestSweepExpired:
    async def test_rolls_back_expired_leases_with_reason_ttl_expired(self):
        ledger = FakeLedger()
        ledger.expired = [_view(id="lease-old"), _view(id="lease-older")]
        executor = RecordingExecutor()

        summary = await sweep_expired(ledger, FakeRegistry(executor))

        assert summary["expired"] == 2
        assert summary["rolled_back"] == 2
        assert summary["errors"] == 0
        marks = [c for c in ledger.calls if c[0] == "mark_rolled_back"]
        assert {m[1] for m in marks} == {"lease-old", "lease-older"}
        assert {m[2] for m in marks} == {TTL_EXPIRED}

    async def test_missing_executor_is_skipped_never_rolled_back(self):
        """A missing executor must never be mistaken for a rollback."""
        ledger = FakeLedger()
        ledger.expired = [_view(id="lease-old", action_type="tarpit")]

        summary = await sweep_expired(ledger, FakeRegistry(None))

        assert summary["skipped_no_executor"] == 1
        assert summary["rolled_back"] == 0
        assert not any(c[0] == "mark_rolled_back" for c in ledger.calls)

    async def test_one_bad_lease_does_not_stop_the_sweep(self):
        ledger = FakeLedger()
        ledger.expired = [_view(id="lease-bad"), _view(id="lease-good")]
        executor = RecordingExecutor(undo_raises=True)

        summary = await sweep_expired(ledger, FakeRegistry(executor))

        assert summary["errors"] == 2
        assert summary["rolled_back"] == 0
        # No row closed behind a failed undo.
        assert not any(c[0] == "mark_rolled_back" for c in ledger.calls)


# ----------------------------------------------------------------------
# reconcile_stale_intents — the crash window
# ----------------------------------------------------------------------


class TestReconcileStaleIntents:
    async def test_fresh_stale_intent_is_retried_idempotently(self):
        ledger = FakeLedger()
        ledger.stale = [_view(id="lease-stuck", status="pending_apply")]
        executor = RecordingExecutor()

        summary = await reconcile_stale_intents(
            ledger, FakeRegistry(executor), apply_timeout_seconds=30
        )

        assert summary["retried_applied"] == 1
        assert len(executor.apply_calls) == 1
        mark = next(c for c in ledger.calls if c[0] == "mark_applied")
        assert mark[1] == "lease-stuck"

    async def test_intent_past_its_own_expiry_is_never_applied(self):
        ledger = FakeLedger()
        ledger.stale = [
            _view(
                id="lease-late",
                status="pending_apply",
                expires_at=utcnow() - timedelta(seconds=1),
            )
        ]
        executor = RecordingExecutor()

        summary = await reconcile_stale_intents(
            ledger, FakeRegistry(executor), apply_timeout_seconds=30
        )

        assert summary["aborted_failed"] == 1
        assert executor.apply_calls == []  # NEVER applied past expiry
        # The idempotent uncertainty undo still runs — with the STORED
        # payload — then the row fails.
        assert executor.undo_calls == [("lease-late", {"rule_id": "r-1"})]
        failed = next(c for c in ledger.calls if c[0] == "mark_failed")
        assert failed[2] == REASON_TTL_EXPIRED_BEFORE_APPLY

    async def test_intent_without_an_executor_aborts(self):
        ledger = FakeLedger()
        ledger.stale = [_view(id="lease-orphan", status="pending_apply")]

        summary = await reconcile_stale_intents(
            ledger, FakeRegistry(None), apply_timeout_seconds=30
        )

        assert summary["aborted_failed"] == 1
        failed = next(c for c in ledger.calls if c[0] == "mark_failed")
        assert failed[2] == REASON_NO_EXECUTOR

    async def test_failed_retry_undoes_then_marks_failed(self):
        ledger = FakeLedger()
        ledger.stale = [_view(id="lease-stuck", status="pending_apply")]
        executor = RecordingExecutor(apply_raises=True)

        summary = await reconcile_stale_intents(
            ledger, FakeRegistry(executor), apply_timeout_seconds=30
        )

        assert summary["aborted_failed"] == 1
        assert executor.undo_calls == [("lease-stuck", {})]
        failed = next(c for c in ledger.calls if c[0] == "mark_failed")
        assert failed[2] == REASON_APPLY_RETRY_FAILED


# ----------------------------------------------------------------------
# The CAS — compare-and-swap over the row's status (no_db seam)
# ----------------------------------------------------------------------


@pytest.fixture
def no_db():
    """Mocked db manager around ONE stable session instance: the ledger
    opens a scope per call, and the tests configure the rowcount that
    every scope yields, so the CAS can be exercised without PostgreSQL."""
    manager = MagicMock()
    session = MagicMock()

    @contextmanager
    def _scope():
        yield session

    manager.session_scope = _scope
    with patch("core.response.fastpath.ledger.get_db_manager", return_value=manager):
        yield session


class TestCasTransitions:
    def test_mark_applied_transitions_when_the_row_is_still_pending(self, no_db):
        no_db.execute.return_value.rowcount = 1

        transition = ContainmentLedger().mark_applied(
            "lease-1", {"rule_id": "r-1"}, ACTOR_SWEEPER, "ev-7"
        )

        assert transition is not None
        assert transition.from_status == "pending_apply"
        assert transition.to_status == "applied"
        assert transition.actor == ACTOR_SWEEPER
        assert transition.evidence_version == "ev-7"

    def test_cas_refuses_a_stale_status(self, no_db):
        """rowcount == 0 — the row moved under us (adjudication vs. the
        sweep). The loser is refused, never errors, never double-applies."""
        no_db.execute.return_value.rowcount = 0

        transition = ContainmentLedger().mark_applied(
            "lease-1", {"rule_id": "r-1"}, ACTOR_SWEEPER, None
        )

        assert transition is None

    def test_mark_failed_covers_both_active_states(self, no_db):
        no_db.execute.return_value.rowcount = 1

        transition = ContainmentLedger().mark_failed(
            "lease-1", REASON_APPLY_FAILED, ACTOR_SWEEPER, None
        )

        assert transition is not None
        assert transition.from_status == "active"  # either active state
        assert transition.to_status == "failed"


# ----------------------------------------------------------------------
# Dataclasses and the lease spec
# ----------------------------------------------------------------------


class TestLeaseShapes:
    def test_intent_idempotency_key_is_type_entity(self):
        assert _intent().idempotency_key == "challenge:ip:203.0.113.7"

    def test_view_from_row_maps_every_field(self):
        row = ContainmentAction(
            action_type="challenge",
            entity_type="ip",
            entity_id="203.0.113.7",
            idempotency_key="challenge:ip:203.0.113.7",
            decision_rule="severity >= high",
            observed={"severity": "critical"},
            undo_payload={"rule_id": "r-1"},
            expires_at=utcnow(),
            ttl_seconds=300,
        )
        row.id = "lease-x"  # default_lease_id runs server-side otherwise

        view = LeaseView.from_row(row)

        assert view.id == "lease-x"
        assert view.undo_payload == {"rule_id": "r-1"}
        assert view.observed == {"severity": "critical"}
        assert view.is_shadow is False
        assert view.ttl_seconds == 300

    def test_lease_spec_carries_the_executor_fields(self):
        spec = lease_spec_of(_view())
        assert spec.lease_id == "lease-1"
        assert spec.action_type == "challenge"
        assert spec.entity_id == "203.0.113.7"
        assert spec.observed == {"severity": "critical", "confidence": 0.93}


# ----------------------------------------------------------------------
# Redis is optional — the ledger path never notices
# ----------------------------------------------------------------------


class TestLedgerNeedsNoRedis:
    def test_no_redis_dependency_in_the_ledger_module(self):
        """The DB ledger is the source of truth; Redis only ever
        accelerates dedup elsewhere. Structural pin: the ledger module
        contains no redis import, and the drivers orchestrate fine while
        the shared redis client degrades to None."""
        source = inspect.getsource(ledger_module)
        assert "import redis" not in source
        assert "from redis" not in source

    async def test_drivers_function_while_the_redis_driver_is_missing(
        self, monkeypatch
    ):
        """With the redis driver unavailable, ``get_async_redis`` returns
        None (the in-memory degradation contract) — and the lease drivers
        orchestrate exactly as before, because the DB ledger is the
        source of truth and the fastpath package never touches Redis."""
        import sys

        ledger = FakeLedger(leases={"lease-1": _view()})
        ledger.expired = [_view(id="lease-1")]
        executor = RecordingExecutor()

        from core import redis_client

        monkeypatch.setattr(redis_client, "_client", None)
        with patch.dict(sys.modules, {"redis": None}):
            assert redis_client.get_async_redis("fastpath-tests") is None

        transition, summary = await asyncio.gather(
            rollback_lease(ledger, executor, "lease-1", TTL_EXPIRED),
            sweep_expired(ledger, FakeRegistry(executor)),
        )

        assert transition is not None
        assert summary["rolled_back"] == 1
