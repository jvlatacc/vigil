"""containment_actions — the lease ledger's uniqueness rule.

A lease is the applied-effect record for speculative containment: one ACTIVE
lease per idempotency key ``{action_type}:{entity_type}:{entity_id}``. Active
means pending_apply or applied; failed, rolled_back and escalated are terminal
and free the key, so a retry after a failure is allowed — the partial-index
idiom of approval_actions (#827), narrowed to the two active states.

The scratch database holds only containment_actions, built from the model, so
the real columns and the real partial index are exercised.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.storage.models import ContainmentAction
from core.time import utcnow

pytestmark = [pytest.mark.integration, pytest.mark.database]

SCRATCH_DB = "vigil_test_containment_ledger"

# These fixtures CREATE and DROP a database. Only ever against a loopback
# host — a developer whose POSTGRES_HOST points at a shared or staging server
# must get a skip, not a dropped database.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "0.0.0.0"}

_CONNECT_ARGS = {"connect_timeout": 5}


def _host() -> str:
    return os.getenv("POSTGRES_HOST", "localhost")


def _url(database: str) -> str:
    user = os.getenv("POSTGRES_USER", "deeptempo")
    password = os.getenv("POSTGRES_PASSWORD", "deeptempo_secure_password_change_me")
    host = _host()
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


def _admin_engine():
    return create_engine(
        _url("postgres"), isolation_level="AUTOCOMMIT", connect_args=_CONNECT_ARGS
    )


SCRATCH_URL = _url(SCRATCH_DB)


def _requires_local_postgres() -> str | None:
    """Skip reason, evaluated per test: probing at import would open a
    connection during collection and stall the run on an unreachable host."""
    if _host() not in _LOCAL_HOSTS:
        return (
            f"refusing to CREATE/DROP a database on non-local POSTGRES_HOST "
            f"{_host()!r}"
        )
    try:
        with _admin_engine().connect():
            return None
    except Exception as e:  # noqa: BLE001
        return f"requires a local PostgreSQL (docker compose up -d postgres): {e}"


@pytest.fixture
def ledger_db():
    reason = _requires_local_postgres()
    if reason:
        pytest.skip(reason)

    admin = _admin_engine()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))

    scratch = create_engine(SCRATCH_URL)
    ContainmentAction.__table__.create(scratch)

    yield scratch

    scratch.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
    admin.dispose()


def _make_lease(**overrides) -> ContainmentAction:
    """A pending_apply lease with the idempotency-key shape the gate will use."""
    fields = dict(
        action_type="fp_rate_limit",
        entity_type="ip",
        entity_id="203.0.113.7",
        idempotency_key="fp_rate_limit:ip:203.0.113.7",
        decision_rule="severity >= high and action_type enabled",
        observed={
            "severity": "critical",
            "confidence": 0.93,
            "detector": "credential_stuffing",
        },
        expires_at=utcnow(),
        ttl_seconds=300,
    )
    fields.update(overrides)
    return ContainmentAction(**fields)


@pytest.mark.parametrize("active_status", ["pending_apply", "applied"])
def test_second_active_lease_with_same_key_is_rejected(ledger_db, active_status):
    with Session(ledger_db) as session:
        lease = _make_lease()
        session.add(lease)
        session.commit()

        lease.status = active_status
        if active_status == "applied":
            lease.applied_at = utcnow()
        session.commit()

        # The replay case: the trigger fired twice for the same principal.
        session.add(_make_lease(id="lease-replay"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.parametrize("terminal", ["failed", "rolled_back", "escalated"])
def test_terminal_state_frees_the_key(ledger_db, terminal):
    with Session(ledger_db) as session:
        lease = _make_lease()
        session.add(lease)
        session.commit()

        lease.status = terminal
        lease.rolled_back_at = utcnow() if terminal != "failed" else None
        if terminal == "rolled_back":
            lease.rollback_reason = "downgraded"
        session.commit()

        # A fresh lease with new evidence is exactly why terminal states
        # are outside the partial index's predicate.
        retried = _make_lease(id="lease-retry")
        retried.status = "pending_apply"
        session.add(retried)
        session.commit()


def test_a_different_key_is_never_blocked(ledger_db):
    with Session(ledger_db) as session:
        session.add(_make_lease())
        session.add(
            _make_lease(
                id="lease-other",
                entity_id="203.0.113.8",
                idempotency_key="fp_rate_limit:ip:203.0.113.8",
            )
        )
        session.commit()

