"""The edge tables apply cleanly — twice — and enforce what the mesh leans on.

compose's db-seed and Helm's db-init Job apply ``infra/database/init/*.sql``
on every install and every upgrade, so each file must be idempotent: a second
run is the normal path, not an edge case (compose re-applies the whole
directory after create_all on every ``up``). This provisions a scratch
database, applies the three edge files in order, then applies them again and
asserts the second run changed nothing.

The behavior half asserts, against that applied SQL, the constraints the edge
API builds on: one token hash per node, one active policy per node, one
receipt per journal range, and the all-or-nothing revocation records.

psql is the applier — compose and the schema-snapshot machinery both apply
init SQL through it, and a statement splitter would not reproduce its
behavior.
"""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import ARRAY, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.integration, pytest.mark.database]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INIT_SQL = REPO_ROOT / "infra" / "database" / "init"

EDGE_FILES = [
    "40_edge_nodes.sql",
    "41_edge_policies.sql",
    "42_edge_journal_receipts.sql",
]

EDGE_TABLES = ("edge_nodes", "edge_policies", "edge_journal_receipts")

SCRATCH_DB = "vigil_test_edge_schema"


def _params() -> tuple[str, str, str, str]:
    """User, password, host, port from POSTGRES_*, the knobs DatabaseManager
    reads. CI's integration job uses test/test/deeptempo_test; a developer's
    compose stack uses the deeptempo defaults. Hardcoding either makes the
    test silently skip in the other environment."""
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
    """Apply one init SQL file, failing on the first error.

    Strict where the snapshot generator is tolerant: these three files are
    self-contained (no create_all prerequisites), so "applies cleanly" means
    exit 0 with nothing swallowed.
    """
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


def _structure(engine: Engine) -> dict:
    """Everything the edge tables declare: columns, keys, constraints, indexes."""
    insp = inspect(engine)
    dump: dict = {}
    for table in EDGE_TABLES:
        dump[table] = {
            "columns": {
                column["name"]: (column["type"], column["nullable"])
                for column in insp.get_columns(table)
            },
            "pk": insp.get_pk_constraint(table)["constrained_columns"],
            "checks": sorted(
                check["name"] for check in insp.get_check_constraints(table)
            ),
            "indexes": sorted(index["name"] for index in insp.get_indexes(table)),
            "fks": sorted(
                (foreign["constrained_columns"][0], foreign["referred_table"])
                for foreign in insp.get_foreign_keys(table)
            ),
        }
    return dump


@pytest.fixture
def edge_db():
    """A scratch database with the three edge files applied, in order."""
    admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))

    scratch = create_engine(_url(SCRATCH_DB))
    for name in EDGE_FILES:
        _apply_psql(INIT_SQL / name)

    yield scratch

    scratch.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def clean_edge_db(edge_db):
    """edge_db with the three tables emptied between behavior tests."""
    with edge_db.connect() as conn:
        conn.execute(
            text("TRUNCATE edge_journal_receipts, edge_policies, edge_nodes CASCADE")
        )
        conn.commit()
    yield edge_db


def _insert(conn, sql: str, **params) -> None:
    conn.execute(text(sql), params)
    conn.commit()


# --- schema application -------------------------------------------------------


def _canonical(structure: dict) -> dict:
    """A stringified copy of a structure dump, for before/after equality —
    fresh type objects from two inspections never compare equal."""
    return {
        table: {
            **data,
            "columns": {
                name: (str(kind), nullable)
                for name, (kind, nullable) in data["columns"].items()
            },
        }
        for table, data in structure.items()
    }


def test_edge_files_apply_and_rerun_cleanly(edge_db):
    before = _canonical(_structure(edge_db))
    for table in EDGE_TABLES:
        assert before[table]["columns"], f"{table}: not created by the edge files"

    # The second run is the compose/upgrade path: IF NOT EXISTS everywhere,
    # no error, no drift.
    for name in EDGE_FILES:
        _apply_psql(INIT_SQL / name)
    assert _canonical(_structure(edge_db)) == before


def test_edge_tables_carry_the_expected_columns(edge_db):
    structure = _structure(edge_db)

    assert set(structure["edge_nodes"]["columns"]) == {
        "node_id",
        "token_hash",
        "segment_labels",
        "status",
        "last_seen",
        "enrolled_at",
        "enrolled_by",
        "revoked_at",
        "revoked_by",
        "revocation_reason",
    }
    assert structure["edge_nodes"]["pk"] == ["node_id"]

    assert set(structure["edge_policies"]["columns"]) == {
        "node_id",
        "policy_version",
        "envelope",
        "payload_hash",
        "signing_key_ids",
        "status",
        "not_before",
        "not_after",
        "created_at",
        "created_by",
        "activated_at",
        "revoked_at",
    }
    assert structure["edge_policies"]["pk"] == ["node_id", "policy_version"]

    assert set(structure["edge_journal_receipts"]["columns"]) == {
        "receipt_id",
        "node_id",
        "policy_version",
        "first_seq",
        "last_seq",
        "chain_head",
        "record_count",
        "accepted_at",
    }
    assert structure["edge_journal_receipts"]["pk"] == ["receipt_id"]

    # The types the safety properties hang on: hashes are sha256 hex, the
    # envelope is JSONB, labels and key ids are text arrays. (Array columns
    # surface as a generic ARRAY type from the inspector, so they are checked
    # by class — the element type lives in the model test.)
    node_types = {
        name: kind for name, (kind, _) in structure["edge_nodes"]["columns"].items()
    }
    assert str(node_types["token_hash"]) == "VARCHAR(64)"
    assert isinstance(node_types["segment_labels"], ARRAY)
    policy_types = {
        name: kind for name, (kind, _) in structure["edge_policies"]["columns"].items()
    }
    assert str(policy_types["envelope"]) == "JSONB"
    assert str(policy_types["payload_hash"]) == "VARCHAR(64)"
    assert isinstance(policy_types["signing_key_ids"], ARRAY)
    receipt_types = {
        name: kind
        for name, (kind, _) in structure["edge_journal_receipts"]["columns"].items()
    }
    assert str(receipt_types["chain_head"]) == "VARCHAR(64)"


def test_edge_policies_and_receipts_reference_edge_nodes(edge_db):
    structure = _structure(edge_db)
    expected = [("node_id", "edge_nodes")]
    assert structure["edge_policies"]["fks"] == expected
    assert structure["edge_journal_receipts"]["fks"] == expected


# --- the constraints the edge API builds on -----------------------------------


def test_token_hash_is_unique_per_node(clean_edge_db):
    with clean_edge_db.connect() as conn:
        _insert(
            conn,
            "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by) "
            "VALUES ('wn-aaaa', :token_hash, 'ops-1')",
            token_hash="a" * 64,
        )
        with pytest.raises(IntegrityError):
            _insert(
                conn,
                "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by) "
                "VALUES ('wn-bbbb', :token_hash, 'ops-1')",
                token_hash="a" * 64,
            )
        conn.rollback()
        # A distinct hash for a distinct identity is fine.
        _insert(
            conn,
            "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by) "
            "VALUES ('wn-bbbb', :token_hash, 'ops-1')",
            token_hash="b" * 64,
        )


def test_node_revocation_record_is_all_or_nothing(clean_edge_db):
    with clean_edge_db.connect() as conn:
        # Active rows carry no revocation record.
        with pytest.raises(IntegrityError):
            _insert(
                conn,
                "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by, revoked_at) "
                "VALUES ('wn-aaaa', :token_hash, 'ops-1', NOW())",
                token_hash="a" * 64,
            )
        conn.rollback()
        # A revoked row carries the whole record: when, by whom.
        with pytest.raises(IntegrityError):
            _insert(
                conn,
                "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by, status, "
                "revoked_at) VALUES ('wn-aaaa', :token_hash, 'ops-1', 'revoked', NOW())",
                token_hash="a" * 64,
            )
        conn.rollback()
        _insert(
            conn,
            "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by, status, "
            "revoked_at, revoked_by) "
            "VALUES ('wn-aaaa', :token_hash, 'ops-1', 'revoked', NOW(), 'ops-1')",
            token_hash="a" * 64,
        )


def test_policy_version_is_monotonic_per_node(clean_edge_db):
    active_policy = (
        "INSERT INTO edge_policies (node_id, policy_version, envelope, payload_hash, "
        "signing_key_ids, status, not_before, not_after, created_by, activated_at) "
        "VALUES ('wn-aaaa', :version, CAST(:envelope AS JSONB), :payload_hash, "
        "ARRAY[:key_id], 'active', NOW() - INTERVAL '1 hour', "
        "NOW() + INTERVAL '1 hour', 'ops-1', NOW())"
    )
    envelope = '{"payloadType": "application/vnd.deeptempo.vigil.edge-policy.v1+json"}'
    with clean_edge_db.connect() as conn:
        _insert(
            conn,
            "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by) "
            "VALUES ('wn-aaaa', :token_hash, 'ops-1')",
            token_hash="a" * 64,
        )
        _insert(
            conn,
            active_policy,
            version=42,
            envelope=envelope,
            payload_hash="p" * 64,
            key_id="k1",
        )
        # The same version twice is not a stream — reject, even when the
        # re-presented pack hashes differently (tamper/replay detection).
        with pytest.raises(IntegrityError):
            _insert(
                conn,
                active_policy,
                version=42,
                envelope=envelope,
                payload_hash="q" * 64,
                key_id="k1",
            )


def test_one_active_policy_per_node(clean_edge_db):
    active_policy = (
        "INSERT INTO edge_policies (node_id, policy_version, envelope, payload_hash, "
        "signing_key_ids, status, not_before, not_after, created_by, activated_at) "
        "VALUES ('wn-aaaa', :version, CAST(:envelope AS JSONB), :payload_hash, "
        "ARRAY[:key_id], 'active', NOW() - INTERVAL '1 hour', "
        "NOW() + INTERVAL '1 hour', 'ops-1', NOW())"
    )
    envelope = '{"payloadType": "application/vnd.deeptempo.vigil.edge-policy.v1+json"}'
    with clean_edge_db.connect() as conn:
        _insert(
            conn,
            "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by) "
            "VALUES ('wn-aaaa', :token_hash, 'ops-1')",
            token_hash="a" * 64,
        )
        _insert(
            conn,
            active_policy,
            version=42,
            envelope=envelope,
            payload_hash="p" * 64,
            key_id="k1",
        )
        # A second active policy for the same node has no single meaning.
        with pytest.raises(IntegrityError):
            _insert(
                conn,
                active_policy,
                version=43,
                envelope=envelope,
                payload_hash="q" * 64,
                key_id="k1",
            )
        conn.rollback()
        # ...but the successor after revocation is exactly how a policy rolls.
        _insert(
            conn,
            "UPDATE edge_policies SET status = 'revoked', revoked_at = NOW() "
            "WHERE node_id = 'wn-aaaa' AND policy_version = 42",
        )
        _insert(
            conn,
            active_policy,
            version=43,
            envelope=envelope,
            payload_hash="q" * 64,
            key_id="k1",
        )


def test_policy_window_must_be_ordered(clean_edge_db):
    with clean_edge_db.connect() as conn:
        _insert(
            conn,
            "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by) "
            "VALUES ('wn-aaaa', :token_hash, 'ops-1')",
            token_hash="a" * 64,
        )
        with pytest.raises(IntegrityError):
            _insert(
                conn,
                "INSERT INTO edge_policies (node_id, policy_version, envelope, "
                "payload_hash, signing_key_ids, not_before, not_after, created_by) "
                "VALUES ('wn-aaaa', 1, CAST(:envelope AS JSONB), :payload_hash, "
                "ARRAY['k1'], NOW() + INTERVAL '1 hour', NOW(), 'ops-1')",
                envelope="{}",
                payload_hash="p" * 64,
            )


def test_receipt_range_is_idempotent_per_node(clean_edge_db):
    receipt = (
        "INSERT INTO edge_journal_receipts (receipt_id, node_id, policy_version, "
        "first_seq, last_seq, chain_head, record_count) "
        "VALUES (:receipt_id, 'wn-aaaa', 42, :first_seq, :last_seq, :chain_head, 3)"
    )
    with clean_edge_db.connect() as conn:
        _insert(
            conn,
            "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by) "
            "VALUES ('wn-aaaa', :token_hash, 'ops-1')",
            token_hash="a" * 64,
        )
        _insert(
            conn,
            receipt,
            receipt_id="receipt-1",
            first_seq=100,
            last_seq=102,
            chain_head="h" * 64,
        )
        # The same range re-pushed on a flaky link resolves to one receipt,
        # not a second merge.
        with pytest.raises(IntegrityError):
            _insert(
                conn,
                receipt,
                receipt_id="receipt-2",
                first_seq=100,
                last_seq=102,
                chain_head="h" * 64,
            )
        conn.rollback()
        # A later batch from the same node is a different range.
        _insert(
            conn,
            receipt,
            receipt_id="receipt-2",
            first_seq=103,
            last_seq=105,
            chain_head="i" * 64,
        )


def test_receipt_range_must_be_ordered_and_nonempty(clean_edge_db):
    with clean_edge_db.connect() as conn:
        _insert(
            conn,
            "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by) "
            "VALUES ('wn-aaaa', :token_hash, 'ops-1')",
            token_hash="a" * 64,
        )
        with pytest.raises(IntegrityError):
            _insert(
                conn,
                "INSERT INTO edge_journal_receipts (receipt_id, node_id, "
                "policy_version, first_seq, last_seq, chain_head, record_count) "
                "VALUES ('receipt-1', 'wn-aaaa', 42, 103, 100, :chain_head, 3)",
                chain_head="h" * 64,
            )
        conn.rollback()
        with pytest.raises(IntegrityError):
            _insert(
                conn,
                "INSERT INTO edge_journal_receipts (receipt_id, node_id, "
                "policy_version, first_seq, last_seq, chain_head, record_count) "
                "VALUES ('receipt-1', 'wn-aaaa', 42, 100, 102, :chain_head, 0)",
                chain_head="h" * 64,
            )


def test_journal_receipt_cites_an_enrolled_node(clean_edge_db):
    with clean_edge_db.connect() as conn:
        with pytest.raises(IntegrityError):
            _insert(
                conn,
                "INSERT INTO edge_journal_receipts (receipt_id, node_id, "
                "policy_version, first_seq, last_seq, chain_head, record_count) "
                "VALUES ('receipt-1', 'wn-orphan', 42, 100, 102, :chain_head, 3)",
                chain_head="h" * 64,
            )


def test_deleting_a_node_cascades(clean_edge_db):
    with clean_edge_db.connect() as conn:
        _insert(
            conn,
            "INSERT INTO edge_nodes (node_id, token_hash, enrolled_by) "
            "VALUES ('wn-aaaa', :token_hash, 'ops-1')",
            token_hash="a" * 64,
        )
        _insert(
            conn,
            "INSERT INTO edge_policies (node_id, policy_version, envelope, "
            "payload_hash, signing_key_ids, not_before, not_after, created_by) "
            "VALUES ('wn-aaaa', 42, CAST(:envelope AS JSONB), :payload_hash, "
            "ARRAY['k1'], NOW(), NOW() + INTERVAL '1 hour', 'ops-1')",
            envelope="{}",
            payload_hash="p" * 64,
        )
        _insert(
            conn,
            "INSERT INTO edge_journal_receipts (receipt_id, node_id, policy_version, "
            "first_seq, last_seq, chain_head, record_count) "
            "VALUES ('receipt-1', 'wn-aaaa', 42, 100, 102, :chain_head, 3)",
            chain_head="h" * 64,
        )
        _insert(conn, "DELETE FROM edge_nodes WHERE node_id = 'wn-aaaa'")
        receipts = (
            conn.execute(text("SELECT count(*) FROM edge_journal_receipts")).scalar(),
        )
        policies = conn.execute(text("SELECT count(*) FROM edge_policies")).scalar()
    assert receipts[0] == 0
    assert policies == 0
