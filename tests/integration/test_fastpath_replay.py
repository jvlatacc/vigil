"""Replay, shadow-close, and the read surface against a real PostgreSQL.

The unit suite proves the adjudicators' ORCHESTRATION (what happens when,
and in what order); this suite proves the DATASTORE-ENFORCED half of the
contract. The replay invariant — a duplicate trigger collapses into the
live row and the executor never runs twice — is a race against a real
uniqueness constraint, so it runs against a scratch database, the
test_fastpath_sweep pattern: seeded rows, the same entry points the
daemon and the router call, and the actual row states they leave behind.
"""

import os
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Dict, List

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from core.response.fastpath.adjudication import (
    close_expired_shadow_rows,
    get_lease_by_id,
    read_leases,
)
from core.response.fastpath.ledger import (
    REASON_TTL_EXPIRED_BEFORE_APPLY,
    ApplyOutcome,
    ContainmentLedger,
    LeaseIntent,
    LeaseView,
    issue_and_apply,
)
from core.storage.models import ContainmentAction
from core.time import utcnow

pytestmark = [pytest.mark.integration, pytest.mark.database]

SCRATCH_DB = "vigil_test_fastpath_replay"

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
    """The executor call count is the assertion — replays must not reach it."""

    def __init__(self) -> None:
        self.apply_calls: List[Any] = []
        self.undo_calls: List[Any] = []

    async def apply(self, lease) -> Dict[str, Any]:
        self.apply_calls.append(lease)
        return {"rule_id": f"rule-for-{lease.lease_id}"}

    async def undo(self, lease_id: str, undo_payload: Dict[str, Any]) -> None:
        self.undo_calls.append((lease_id, dict(undo_payload or {})))


@pytest.fixture
def replay_db():
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
        try:
            c.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))
        except ProgrammingError as e:
            # A local server that connects but cannot hand out scratch
            # databases is a half-configured developer account — grant
            # CREATEDB locally; CI's service user has it.
            pytest.skip(f"the local account cannot create a scratch database: {e}")

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
    action_type: str = "fp_rate_limit",
    expires_at=None,
    created_at=None,
    undo_payload: Dict | None = None,
    is_shadow: bool = False,
    entity_id: str = "203.0.113.7",
    observed: Dict | None = None,
) -> str:
    lease = ContainmentAction(
        action_type=action_type,
        entity_type="ip",
        entity_id=entity_id,
        idempotency_key=f"{action_type}:ip:{entity_id}",
        decision_rule="severity >= high and action_type enabled",
        observed=observed or {"severity": "critical", "confidence": 0.93},
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


def _rows(engine) -> List[ContainmentAction]:
    with Session(engine) as session:
        return list(session.execute(select(ContainmentAction)).scalars().all())


def _intent(entity_id: str = "203.0.113.7", finding_id: str = "f-1") -> LeaseIntent:
    return LeaseIntent(
        action_type="fp_rate_limit",
        entity_type="ip",
        entity_id=entity_id,
        ttl_seconds=300,
        decision_rule="fastpath.gate.issue severity=critical",
        observed={"severity": "critical", "confidence": 0.95, "detector": "ids"},
        finding_id=finding_id,
    )


# ----------------------------------------------------------------------
# Replay — a duplicate trigger collapses into the live row
# ----------------------------------------------------------------------


class TestReplay:
    async def test_a_duplicate_trigger_is_one_row_and_one_apply(self, replay_db):
        ledger = ContainmentLedger(db_manager=EngineSessionManager(replay_db))
        executor = RecordingExecutor()

        first: ApplyOutcome = await issue_and_apply(ledger, _intent(), executor)
        second: ApplyOutcome = await issue_and_apply(ledger, _intent(), executor)

        assert first.applied is True
        assert second.replay is True
        assert second.applied is False
        # Same live row, same key — the duplicate trigger saw the lease
        # that was already running, not a second chance to apply.
        assert second.lease.id == first.lease.id
        assert second.lease.idempotency_key == "fp_rate_limit:ip:203.0.113.7"

    async def test_the_executor_never_runs_twice_for_one_entity(self, replay_db):
        ledger = ContainmentLedger(db_manager=EngineSessionManager(replay_db))
        executor = RecordingExecutor()

        await issue_and_apply(ledger, _intent(), executor)
        await issue_and_apply(ledger, _intent(), executor)
        await issue_and_apply(ledger, _intent(), executor)

        assert len(executor.apply_calls) == 1

        rows = _rows(replay_db)
        assert len(rows) == 1
        assert rows[0].status == "applied"
        assert rows[0].undo_payload == {"rule_id": f"rule-for-{rows[0].id}"}


# ----------------------------------------------------------------------
# Shadow-row closing — stale shadow rows release the entity's key
# ----------------------------------------------------------------------


class TestShadowClose:
    def test_an_expired_shadow_row_closes_as_failed_ttl_expired(self, replay_db):
        lease_id = _seed(
            replay_db,
            status="pending_apply",
            is_shadow=True,
            expires_at=utcnow() - timedelta(seconds=1),
        )
        manager = EngineSessionManager(replay_db)

        closed = close_expired_shadow_rows(db_manager=manager)

        assert closed == 1
        row = _row(replay_db, lease_id)
        assert row.status == "failed"
        assert row.rollback_reason == REASON_TTL_EXPIRED_BEFORE_APPLY

    def test_a_fresh_shadow_row_stays_open_for_its_window(self, replay_db):
        lease_id = _seed(
            replay_db,
            status="pending_apply",
            is_shadow=True,
            expires_at=utcnow() + timedelta(seconds=300),
        )
        manager = EngineSessionManager(replay_db)

        assert close_expired_shadow_rows(db_manager=manager) == 0
        assert _row(replay_db, lease_id).status == "pending_apply"

    def test_a_live_lease_is_not_the_shadow_closer_business(self, replay_db):
        # An expired LIVE intent belongs to the daemon's sweeper
        # (reconcile_stale_intents), not to the shadow-row closer.
        lease_id = _seed(
            replay_db,
            status="pending_apply",
            is_shadow=False,
            expires_at=utcnow() - timedelta(seconds=1),
        )
        manager = EngineSessionManager(replay_db)

        assert close_expired_shadow_rows(db_manager=manager) == 0
        assert _row(replay_db, lease_id).status == "pending_apply"


# ----------------------------------------------------------------------
# Read surface — the one implementation behind the router and the tool
# ----------------------------------------------------------------------


class TestReadSurface:
    def test_active_read_returns_only_live_leases_newest_first(self, replay_db):
        applied_id = _seed(replay_db, status="applied", undo_payload={"rule_id": "r1"})
        _seed(
            replay_db,
            status="rolled_back",
            entity_id="198.51.100.9",
            created_at=utcnow() - timedelta(seconds=10),
        )
        manager = EngineSessionManager(replay_db)

        leases = read_leases(status="active", db_manager=manager)

        assert [lease.id for lease in leases] == [applied_id]

    def test_all_read_includes_terminal_states_newest_first(self, replay_db):
        older_id = _seed(
            replay_db,
            status="rolled_back",
            entity_id="198.51.100.9",
            created_at=utcnow() - timedelta(seconds=10),
        )
        applied_id = _seed(replay_db, status="applied", undo_payload={"rule_id": "r1"})
        manager = EngineSessionManager(replay_db)

        leases = read_leases(status="all", db_manager=manager)

        assert [lease.id for lease in leases] == [applied_id, older_id]

    def test_entity_filters_narrow_the_read(self, replay_db):
        _seed(replay_db, status="applied", undo_payload={"rule_id": "r1"})
        other_id = _seed(
            replay_db,
            status="applied",
            entity_id="198.51.100.9",
            undo_payload={"rule_id": "r2"},
        )
        manager = EngineSessionManager(replay_db)

        leases = read_leases(
            status="active",
            entity_type="ip",
            entity_id="198.51.100.9",
            db_manager=manager,
        )

        assert [lease.id for lease in leases] == [other_id]

    def test_one_lease_by_id_and_none_for_an_unknown_one(self, replay_db):
        lease_id = _seed(replay_db, status="applied", undo_payload={"rule_id": "r1"})
        manager = EngineSessionManager(replay_db)

        lease: LeaseView = get_lease_by_id(lease_id, db_manager=manager)
        assert lease is not None and lease.id == lease_id
        assert lease.undo_payload == {"rule_id": "r1"}

        assert get_lease_by_id("lease-does-not-exist", db_manager=manager) is None

    def test_an_unknown_status_is_rejected_not_silently_empty(self, replay_db):
        with pytest.raises(ValueError):
            read_leases(status="recent", db_manager=EngineSessionManager(replay_db))
