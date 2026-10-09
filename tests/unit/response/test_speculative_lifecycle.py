"""Idempotency under the speculative lifecycle.

The idempotency key is unique among the rows that still answer for their
target: failed rows free the key so the isolate can be retried (#827), and
rolled_back rows free it so the same target can be restricted again instead
of deduping into its own dead row. The partial unique index (seed 40) and the
service's key lookup carry the same exclusions; these tests pin both.

Distinct keys per test: the throwaway database is session-scoped, so tests
share it in arbitrary order and a reused key would collide with itself.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core.response.approval_service import (
    ActionStatus,
    ActionType,
    ApprovalService,
)
from core.response.config import ResponseConfig
from core.storage.models import ApprovalAction
from core.storage.unit_of_work import unit_of_work

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]

TARGET = "203.0.113.7"


def _row(action_id: str, status: ActionStatus, key: str) -> ApprovalAction:
    return ApprovalAction(
        action_id=action_id,
        action_type=ActionType.RATE_LIMIT.value,
        title="rate limit the source",
        description="speculative containment",
        target=TARGET,
        confidence=0.9,
        reason="fast-path.t1",
        evidence=[],
        created_by="fast-path",
        requires_approval=False,
        status=status.value,
        parameters={},
        idempotency_key=key,
    )


def _key(test_id: str) -> str:
    return f"spec:rate_limit:{test_id}:{TARGET}"


def test_a_live_speculative_row_keeps_its_key(throwaway_database):
    key = _key("t1")
    with unit_of_work() as session:
        session.add(_row("spec-t1-live", ActionStatus.SPECULATIVE, key))
        session.flush()
        session.add(_row("spec-t1-again", ActionStatus.SPECULATIVE, key))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_an_executed_row_still_holds_its_key(throwaway_database):
    # Executed is terminal but still live for its target: a second restriction
    # under the same key dedupes into it, exactly as before this change.
    key = _key("t4")
    with unit_of_work() as session:
        session.add(_row("spec-t4-done", ActionStatus.EXECUTED, key))
        session.flush()
        session.add(_row("spec-t4-dup", ActionStatus.SPECULATIVE, key))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_a_rolled_back_row_frees_its_key(throwaway_database):
    key = _key("t2")
    with unit_of_work() as session:
        session.add(_row("spec-t2-dead", ActionStatus.ROLLED_BACK, key))
    with unit_of_work() as session:
        # The restriction was released; the same target can be restricted again
        # with a fresh row instead of being answered by the dead one.
        session.add(_row("spec-t2-fresh", ActionStatus.SPECULATIVE, key))
        session.flush()
        fetched = session.get(ApprovalAction, "spec-t2-fresh")
        assert fetched is not None
        assert fetched.status == ActionStatus.SPECULATIVE.value


def test_a_failed_row_still_frees_its_key(throwaway_database):
    # The #827 behaviour survives the widened predicate: a failed row is
    # retried, not deduped into.
    key = _key("t5")
    with unit_of_work() as session:
        session.add(_row("spec-t5-broken", ActionStatus.FAILED, key))
    with unit_of_work() as session:
        session.add(_row("spec-t5-retry", ActionStatus.SPECULATIVE, key))
        session.flush()
        fetched = session.get(ApprovalAction, "spec-t5-retry")
        assert fetched is not None


def test_service_refires_after_a_rollback(throwaway_database):
    # The service path: the key lookup behind create_action reads the same
    # exclusions the index does, so a rolled_back row is not returned as the
    # live one and a fresh row is inserted.
    key = _key("t3")
    with unit_of_work() as session:
        session.add(_row("spec-t3-dead", ActionStatus.ROLLED_BACK, key))

    service = ApprovalService(config=ResponseConfig())
    action = service.create_action(
        action_type=ActionType.RATE_LIMIT,
        title="rate limit the source",
        description="speculative containment",
        target=TARGET,
        confidence=0.9,
        reason="fast-path.t1",
        evidence=[],
        created_by="fast-path",
        idempotency_key=key,
        annotate_rule=False,
    )
    # Not the dead row: a fresh row was created for the same key.
    assert action.action_id != "spec-t3-dead"


def test_expires_at_roundtrips_as_tz_aware(throwaway_database):
    # The column is timestamptz (seed 40); a value written aware must come
    # back aware, so the TTL sweep compares like with like.
    expiry = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    with unit_of_work() as session:
        row = _row("spec-t6-timed", ActionStatus.SPECULATIVE, _key("t6"))
        row.expires_at = expiry
        session.add(row)
    with unit_of_work() as session:
        fetched = session.get(ApprovalAction, "spec-t6-timed")
        assert fetched is not None
        assert fetched.expires_at is not None
        assert fetched.expires_at.tzinfo is not None
        assert fetched.expires_at == expiry


def test_the_orm_unique_index_carries_the_rolled_back_exclusion(throwaway_database):
    # The DB-backed tests above run against create_tables(), not the seeds:
    # this pins that the ORM-declared index is the widened one.
    with unit_of_work() as session:
        definition = session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_approval_actions_idempotency_key'"
            )
        ).scalar_one()
    assert "rolled_back" in definition
