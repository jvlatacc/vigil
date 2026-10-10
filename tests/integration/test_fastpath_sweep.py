"""The TTL sweep and intent reconciliation against a real PostgreSQL.

The unit suite proves the drivers' ORCHESTRATION (what happens when, and
in what order); this suite proves the DATASTORE-ENFORCED half of the
contract: seeded rows in a scratch database — expired leases, stuck
intents, shadow rows — and the same entry points the daemon's scheduled
sweep runs, asserting the actual row states the sweeper leaves behind.
Expiry lives in the rows, not in any process's memory, so a crashed
daemon never leaves a lease alive.
"""

import os
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Dict, List

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from core.response.fastpath.ledger import (
    REASON_NO_EXECUTOR,
    REASON_TTL_EXPIRED_BEFORE_APPLY,
    TTL_EXPIRED,
    ContainmentLedger,
    reconcile_stale_intents,
    sweep_expired,
)
from core.storage.models import ContainmentAction
from core.time import utcnow

pytestmark = [pytest.mark.integration, pytest.mark.database]

SCRATCH_DB = "vigil_test_fastpath_sweep"

# These fixtures CREATE and DROP a database. Only ever against a loopback
# host — a developer whose POSTGRES_HOST points at a shared or staging
# server must get a skip, not a dropped database.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "0.0.0.0"}
_CONNECT_ARGS = {"connect_timeout": 5}


def _host() -> str:
    return os.getenv("POSTGRES_HOST", "localhost")


def _url(database: str) -> str:
    user = os.getenv("POSTGRES_USER", "deeptempo")
    password = os.getenv("POSTGRES_PASSWORD", "deeptempo_secure_password_change_me")
    return (
        f"postgresql+psycopg2://{user}:{password}@"
        f"{_host()}:{os.getenv('POSTGRES_PORT', '5432')}/{database}"
    )


def _admin_engine():
    return create_engine(
        _url("postgres"), isolation_level="AUTOCOMMIT", connect_args=_CONNECT_ARGS
    )


class EngineSessionManager:
    """SessionScopeFactory over the scratch engine: the ledger's seam."""

    def __init__(self, engine):
        self._engine = engine

    @contextmanager
    def session_scope(self):
        with Session(self._engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise


class RecordingExecutor:
    """Idempotent fake executor with programmable failures."""

    def __init__(self, *, apply_raises: bool = False):
        self.apply_raises = apply_raises
        self.undo_calls: List[tuple] = []
        self.apply_calls: List[Any] = []

    async def apply(self, lease) -> Dict[str, Any]:
        self.apply_calls.append(lease)
        if self.apply_raises:
            raise RuntimeError("apply exploded")
        return {"rule_id": f"rule-for-{lease.lease_id}"}

    async def undo(self, lease_id: str, undo_payload: Dict[str, Any]) -> None:
        self.undo_calls.append((lease_id, dict(undo_payload or {})))


class RecordingRegistry:
    def __init__(self, executor: Any = None):
        self._executor = executor

    def get(self, action_type: str):
        return self._executor


@pytest.fixture
def sweep_db():
    reason = None
    if _host() not in _LOCAL_HOSTS:
        reason = f"refusing to CREATE/DROP a database on non-local host {_host()!r}"
    else:
        try:
            with _admin_engine().connect():
                pass
        except Exception as e:  # noqa: BLE001
            reason = f"requires a local PostgreSQL (docker compose up -d postgres): {e}"
    if reason:
        pytest.skip(reason)

    admin = _admin_engine()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))

    scratch = create_engine(_url(SCRATCH_DB), connect_args=_CONNECT_ARGS)
    ContainmentAction.__table__.create(scratch)

    yield scratch

    scratch.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
    admin.dispose()


def _seed(
    engine,
    *,
    status: str,
    action_type: str = "challenge",
    expires_at=None,
    created_at=None,
    undo_payload: Dict | None = None,
    is_shadow: bool = False,
    entity_id: str = "203.0.113.7",
) -> str:
    lease = ContainmentAction(
        action_type=action_type,
        entity_type="ip",
        entity_id=entity_id,
        idempotency_key=f"{action_type}:ip:{entity_id}",
        decision_rule="severity >= high and action_type enabled",
        observed={"severity": "critical", "confidence": 0.93},
        status=status,
        expires_at=expires_at or (utcnow() + timedelta(seconds=300)),
        ttl_seconds=300,
        undo_payload=undo_payload,
        is_shadow=is_shadow,
        created_at=created_at or utcnow(),
    )
    with Session(engine) as session:
        session.add(lease)
        session.commit()
        session.refresh(lease)
        return lease.id


def _row(engine, lease_id: str) -> ContainmentAction:
    with Session(engine) as session:
        return session.get(ContainmentAction, lease_id)


def _ledger(engine) -> ContainmentLedger:
    return ContainmentLedger(db_manager=EngineSessionManager(engine))


APPLY_TIMEOUT = 30


# ----------------------------------------------------------------------
# sweep_expired — datastore-enforced expiry
# ----------------------------------------------------------------------


class TestSweepExpired:
    async def test_expired_applied_lease_is_rolled_back_with_ttl_expired(
        self, sweep_db
    ):
        undo = {"rule_id": "rule-123", "ruleset_id": "rs-1"}
        lease_id = _seed(
            sweep_db,
            status="applied",
            expires_at=utcnow() - timedelta(seconds=5),
            undo_payload=undo,
        )
        executor = RecordingExecutor()

        summary = await sweep_expired(_ledger(sweep_db), RecordingRegistry(executor))

        assert summary["rolled_back"] == 1
        assert summary["skipped_no_executor"] == 0
        # The undo ran against the STORED payload, then the row closed.
        assert executor.undo_calls == [(lease_id, undo)]
        row = _row(sweep_db, lease_id)
        assert row.status == "rolled_back"
        assert row.rollback_reason == TTL_EXPIRED

    async def test_unexpired_lease_is_left_alone(self, sweep_db):
        lease_id = _seed(
            sweep_db,
            status="applied",
            expires_at=utcnow() + timedelta(seconds=300),
            undo_payload={"rule_id": "rule-live"},
        )
        executor = RecordingExecutor()

        summary = await sweep_expired(_ledger(sweep_db), RecordingRegistry(executor))

        assert summary["expired"] == 0
        assert executor.undo_calls == []
        assert _row(sweep_db, lease_id).status == "applied"

    async def test_sweep_is_idempotent(self, sweep_db):
        lease_id = _seed(
            sweep_db,
            status="applied",
            expires_at=utcnow() - timedelta(seconds=1),
            undo_payload={"rule_id": "rule-1"},
        )
        executor = RecordingExecutor()
        ledger = _ledger(sweep_db)

        first = await sweep_expired(ledger, RecordingRegistry(executor))
        second = await sweep_expired(ledger, RecordingRegistry(executor))

        assert first["rolled_back"] == 1
        assert second["expired"] == 0
        assert second["rolled_back"] == 0
        assert len(executor.undo_calls) == 1  # the effect was removed once
        assert _row(sweep_db, lease_id).status == "rolled_back"

    async def test_missing_executor_is_skipped_never_rolled_back(self, sweep_db):
        lease_id = _seed(
            sweep_db,
            status="applied",
            action_type="tarpit",  # not registered
            expires_at=utcnow() - timedelta(seconds=1),
            undo_payload={"undo_token": "t-1"},
        )

        summary = await sweep_expired(_ledger(sweep_db), RecordingRegistry(None))

        assert summary["skipped_no_executor"] == 1
        assert summary["rolled_back"] == 0
        # Still live: a missing executor must never pass for a rollback.
        assert _row(sweep_db, lease_id).status == "applied"

    async def test_one_bad_undo_does_not_block_the_rest(self, sweep_db):
        lease_id = _seed(
            sweep_db,
            status="applied",
            expires_at=utcnow() - timedelta(seconds=1),
            undo_payload={"rule_id": "rule-1"},
        )
        other_id = _seed(
            sweep_db,
            status="applied",
            entity_id="198.51.100.9",
            expires_at=utcnow() - timedelta(seconds=2),
            undo_payload={"rule_id": "rule-2"},
        )

        class FlakyExecutor(RecordingExecutor):
            async def undo(self, row_id, undo_payload):  # noqa: ANN001
                if row_id == bad_id:
                    raise RuntimeError("cloudflare 5xx")
                await super().undo(row_id, undo_payload)

        bad_id = lease_id
        executor = FlakyExecutor()

        summary = await sweep_expired(_ledger(sweep_db), RecordingRegistry(executor))

        assert summary["errors"] == 1
        assert summary["rolled_back"] == 1
        # The bad lease stays live for the next sweep; the good one closed.
        assert _row(sweep_db, lease_id).status == "applied"
        assert _row(sweep_db, other_id).status == "rolled_back"


# ----------------------------------------------------------------------
# reconcile_stale_intents — the crash window
# ----------------------------------------------------------------------


class TestReconcileStaleIntents:
    async def test_stuck_intent_is_retried_and_applied(self, sweep_db):
        """A crash between the intent insert and the CAS left a
        pending_apply row; the executor is idempotent, so the reconciler
        retries the apply once and the row lands on its feet."""
        lease_id = _seed(
            sweep_db,
            status="pending_apply",
            created_at=utcnow() - timedelta(seconds=APPLY_TIMEOUT * 10),
        )
        executor = RecordingExecutor()

        summary = await reconcile_stale_intents(
            _ledger(sweep_db), RecordingRegistry(executor), APPLY_TIMEOUT
        )

        assert summary["stale"] == 1
        assert summary["retried_applied"] == 1
        assert len(executor.apply_calls) == 1
        row = _row(sweep_db, lease_id)
        assert row.status == "applied"
        assert row.undo_payload == {"rule_id": f"rule-for-{lease_id}"}

    async def test_stuck_intent_past_its_own_expiry_is_aborted(self, sweep_db):
        """The apply must NEVER land on an intent whose TTL already
        lapsed while it sat stuck — the idempotent undo cleans any
        orphan, then the row fails."""
        lease_id = _seed(
            sweep_db,
            status="pending_apply",
            created_at=utcnow() - timedelta(seconds=APPLY_TIMEOUT * 10),
            expires_at=utcnow() - timedelta(seconds=1),
        )
        executor = RecordingExecutor()

        summary = await reconcile_stale_intents(
            _ledger(sweep_db), RecordingRegistry(executor), APPLY_TIMEOUT
        )

        assert summary["aborted_failed"] == 1
        assert executor.apply_calls == []
        assert executor.undo_calls == [(lease_id, {})]
        row = _row(sweep_db, lease_id)
        assert row.status == "failed"
        assert row.rollback_reason == REASON_TTL_EXPIRED_BEFORE_APPLY

    async def test_intent_without_an_executor_aborts(self, sweep_db):
        lease_id = _seed(
            sweep_db,
            status="pending_apply",
            action_type="tarpit",  # not registered
            created_at=utcnow() - timedelta(seconds=APPLY_TIMEOUT * 10),
        )

        summary = await reconcile_stale_intents(
            _ledger(sweep_db), RecordingRegistry(None), APPLY_TIMEOUT
        )

        assert summary["aborted_failed"] == 1
        row = _row(sweep_db, lease_id)
        assert row.status == "failed"
        assert row.rollback_reason == REASON_NO_EXECUTOR

    async def test_failed_retry_marks_the_row_failed(self, sweep_db):
        lease_id = _seed(
            sweep_db,
            status="pending_apply",
            created_at=utcnow() - timedelta(seconds=APPLY_TIMEOUT * 10),
        )
        executor = RecordingExecutor(apply_raises=True)

        summary = await reconcile_stale_intents(
            _ledger(sweep_db), RecordingRegistry(executor), APPLY_TIMEOUT
        )

        assert summary["aborted_failed"] == 1
        assert executor.undo_calls == [(lease_id, {})]  # uncertainty undo
        assert _row(sweep_db, lease_id).status == "failed"

    async def test_shadow_intent_is_never_reconciled(self, sweep_db):
        """Shadow rows are scored, never applied — retrying an apply for
        one would defeat the whole point of shadow mode."""
        lease_id = _seed(
            sweep_db,
            status="pending_apply",
            is_shadow=True,
            created_at=utcnow() - timedelta(seconds=APPLY_TIMEOUT * 10),
        )
        executor = RecordingExecutor()

        summary = await reconcile_stale_intents(
            _ledger(sweep_db), RecordingRegistry(executor), APPLY_TIMEOUT
        )

        assert summary["stale"] == 0
        assert executor.apply_calls == []
        assert _row(sweep_db, lease_id).status == "pending_apply"
