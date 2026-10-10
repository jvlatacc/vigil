"""Reconcile against a real PostgreSQL — merge, dedupe, gap, legality.

The faked pass (``tests/unit/api/test_api_v1_edge.py``) proves the logic; this
proves the persistence: the dedupe savepoint really rides the unique partial
index on ``approval_actions.idempotency_key`` (30_approval_action_reversibility.sql),
receipts really land in ``edge_journal_receipts``, and merged rows carry the
edge provenance into the JSON ``parameters``.

Applies the init files the reconcile path depends on (workflow_runs ←
approval_actions ← reversibility/idempotency; the three edge files) into a
scratch database — the pattern of ``test_edge_schema_apply.py``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.database]

REPO_ROOT = Path(__file__).resolve().parents[2]
INIT_SQL = REPO_ROOT / "infra" / "database" / "init"

RECONCILE_FILES = [
    "12_workflow_runs.sql",
    "13_approval_actions.sql",
    "30_approval_action_reversibility.sql",
    "40_edge_nodes.sql",
    "41_edge_policies.sql",
    "42_edge_journal_receipts.sql",
]

SCRATCH_DB = "vigil_test_edge_reconcile"
NODE = "wn-7f3a"
TS = "2026-10-09T13:00:00Z"


def _params() -> tuple[str, str, str, str]:
    """User, password, host, port from POSTGRES_* — the knobs DatabaseManager
    reads. Hardcoding CI's or compose's values would silently skip the other."""
    return (
        os.getenv("POSTGRES_USER", "deeptempo"),
        os.getenv("POSTGRES_PASSWORD", "deeptempo_secure_password_change_me"),
        os.getenv("POSTGRES_HOST", "localhost"),
        os.getenv("POSTGRES_PORT", "5432"),
    )


def _url(database: str) -> str:
    user, password, host, port = _params()
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


def _postgres_available() -> bool:
    try:
        eng = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
        with eng.connect():
            return True
    except Exception:
        return False


pytestmark.append(
    pytest.mark.skipif(
        not _postgres_available(),
        reason="requires a local PostgreSQL (docker compose up -d postgres)",
    )
)


def _apply_psql(path: Path) -> None:
    user, password, host, port = _params()
    env = os.environ.copy()
    env.update(
        {
            "PGHOST": host,
            "PGPORT": port,
            "PGUSER": user,
            "PGPASSWORD": password,
            "PGDATABASE": SCRATCH_DB,
        }
    )
    completed = subprocess.run(
        ["psql", "-v", "ON_ERROR_STOP=1", "-q", "-f", str(path)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise AssertionError(
            f"{path.name} did not apply cleanly (exit {completed.returncode}):\n{detail}"
        )


@pytest.fixture()
def reconcile_db():
    """A scratch database with the reconcile path's tables applied."""
    admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))

    scratch = create_engine(_url(SCRATCH_DB))
    for name in RECONCILE_FILES:
        _apply_psql(INIT_SQL / name)

    yield scratch

    scratch.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture()
def db_session(reconcile_db):
    session = sessionmaker(bind=reconcile_db, expire_on_commit=False)()
    yield session
    session.close()


def _seed_node(session, allowed=("block_ip", "unblock_ip"), policy_version: int = 42):
    """An active node and its active signed-policy row, with the allowlist
    baked into the recorded payload (the reconcile legality check reads the
    payload, not a separate column)."""
    from core.storage.models.edge import EdgeNode, EdgePolicy

    payload = json.dumps(
        {"autonomy_envelope": {"allowed_actions": list(allowed)}}
    ).encode()
    session.add(
        EdgeNode(
            node_id=NODE,
            token_hash=hashlib.sha256(b"node-token").hexdigest(),
            segment_labels=["segment:dmz"],
            status="active",
            enrolled_by="test",
        )
    )
    session.add(
        EdgePolicy(
            node_id=NODE,
            policy_version=policy_version,
            envelope={"payload": base64.b64encode(payload).decode()},
            payload_hash=hashlib.sha256(payload).hexdigest(),
            signing_key_ids=["test-key"],
            status="active",
            # ck_edge_policies_activation: an active policy must carry its
            # activation time; window start keeps the fixture deterministic.
            activated_at=datetime(2026, 10, 9, 0, 0, tzinfo=UTC),
            not_before=datetime(2026, 10, 9, 0, 0, tzinfo=UTC),
            not_after=datetime(2026, 10, 10, 0, 0, tzinfo=UTC),
            created_by="test",
        )
    )
    session.commit()


def _edge_node(session):
    from core.storage.models.edge import EdgeNode

    return session.get(EdgeNode, NODE)


def _chained_records(
    *seqs: int, action_type: str = "block_ip", prev: str | None = None
):
    """A valid chained batch from genesis (or ``prev``); returns (records, head)."""
    from core.edge.journal import record_hash

    records: list[dict] = []
    head = prev if prev is not None else "0" * 64
    for seq in seqs:
        record = {
            "seq": seq,
            "ts": TS,
            "mode": "AUTONOMOUS",
            "idempotency_key": f"{action_type}:198.51.100.{seq}",
            "action_type": action_type,
            "target": "198.51.100.7",
            "decision_rule": "edge-001 met (slm 0.93 >= floor 0.90)",
            "execution": {"status": "executed", "executor": "nftables", "at": TS},
            "prev_hash": head,
        }
        head = record_hash(head, record)
        records.append(record)
    return records, head


def _push(records: list[dict], head: str, *, policy_version: int = 42):
    from services.api.routers.edge import JournalPush, JournalRecord

    return JournalPush(
        node_id=NODE,
        policy_version=policy_version,
        chain_head=head,
        records=[JournalRecord(**record) for record in records],
    )


def _approval_count(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM approval_actions")).scalar_one()


def _last_receipt(engine) -> tuple[int, str]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT last_seq, chain_head FROM edge_journal_receipts "
                "ORDER BY last_seq DESC LIMIT 1"
            )
        ).one()
    return row[0], row[1]


# ---------------------------------------------------------------------------
# Merge + dedupe
# ---------------------------------------------------------------------------


def test_merge_writes_edge_provenanced_approval_rows_and_a_receipt(
    db_session, reconcile_db
):
    from services.api.routers.edge import _reconcile

    _seed_node(db_session)
    node = _edge_node(db_session)
    records, head = _chained_records(1, 2)

    response = _reconcile(db_session, node=node, push=_push(records, head))
    db_session.commit()

    assert response.accepted_through == 2
    assert response.merged_count == 2
    assert response.duplicate_ids == []
    assert response.rejected == []
    assert _approval_count(reconcile_db) == 2

    with reconcile_db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action_type, target, status, reversibility, idempotency_key, "
                "created_by, parameters, execution_result FROM approval_actions "
                "ORDER BY idempotency_key"
            )
        ).all()
    assert len(rows) == 2
    for (
        action_type,
        target,
        status,
        reversibility,
        key,
        created_by,
        parameters,
        result,
    ) in rows:
        assert action_type == "block_ip"
        assert target == "198.51.100.7"
        assert status == "executed"
        assert reversibility == "reversible"
        assert created_by == f"edge:{NODE}"
        assert key.startswith("block_ip:")
        assert parameters["source"] == "edge"
        assert parameters["node_id"] == NODE
        assert parameters["policy_version"] == 42
        assert result["executor"] == "nftables"

    assert _last_receipt(reconcile_db) == (2, head)


def test_repushed_batch_dedupes_on_the_real_index(db_session, reconcile_db):
    from services.api.routers.edge import _reconcile

    _seed_node(db_session)
    node = _edge_node(db_session)
    records, head = _chained_records(1)

    first = _reconcile(db_session, node=node, push=_push(records, head))
    db_session.commit()
    assert first.merged_count == 1

    # The same batch arrives again -- at-least-once delivery is the norm.
    again = _reconcile(db_session, node=node, push=_push(records, head))
    db_session.commit()

    assert again.merged_count == 0
    assert again.duplicate_ids == [records[0]["idempotency_key"]]
    assert _approval_count(reconcile_db) == 1  # the unique partial index held
    assert _last_receipt(reconcile_db) == (1, head)  # no phantom watermark advance


# ---------------------------------------------------------------------------
# Gap
# ---------------------------------------------------------------------------


def test_chain_gap_merges_nothing_and_reports_the_resend_position(
    db_session, reconcile_db
):
    from services.api.routers.edge import _reconcile

    _seed_node(db_session)
    node = _edge_node(db_session)
    # Server has accepted seq 1; the node skips ahead to seq 3.
    _, held_head = _chained_records(1)
    gapped, _ = _chained_records(3, prev=held_head)

    response = _reconcile(db_session, node=node, push=_push(gapped, "f" * 64))
    db_session.commit()

    assert response.reason == "seq-gap"
    assert response.server_last_seq == 1
    assert response.server_head == held_head
    assert response.resend_from == 2
    assert _approval_count(reconcile_db) == 0
    with reconcile_db.connect() as conn:
        receipts = conn.execute(
            text("SELECT count(*) FROM edge_journal_receipts")
        ).scalar_one()
    assert receipts == 0


# ---------------------------------------------------------------------------
# Legality
# ---------------------------------------------------------------------------


def test_illegal_records_are_rejected_and_never_merged(db_session, reconcile_db):
    from services.api.routers.edge import _reconcile

    _seed_node(db_session, allowed=("block_ip",))
    node = _edge_node(db_session)
    records, head = _chained_records(1, 2, action_type="process_kill")

    response = _reconcile(db_session, node=node, push=_push(records, head))
    db_session.commit()

    assert response.merged_count == 0
    assert [r.code for r in response.rejected] == [
        "action-not-in-envelope",
        "action-not-in-envelope",
    ]
    # The watermark advances so the refused records are not re-pushed forever.
    assert response.accepted_through == 2
    assert _approval_count(reconcile_db) == 0
    assert _last_receipt(reconcile_db) == (2, head)


def test_unknown_cited_policy_version_rejects_every_record(db_session, reconcile_db):
    from services.api.routers.edge import _reconcile

    _seed_node(db_session)
    node = _edge_node(db_session)
    records, head = _chained_records(1)

    response = _reconcile(
        db_session, node=node, push=_push(records, head, policy_version=99)
    )
    db_session.commit()

    assert [r.code for r in response.rejected] == ["policy-version-unavailable"]
    assert _approval_count(reconcile_db) == 0
