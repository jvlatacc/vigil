"""Migration 40 validated against a real PostgreSQL (spec AC 7's storage half).

The file is executed exactly as provisioning runs it — full content, in
order, twice — and the resulting table, index, grant set and prune
function are asserted from the catalog, not from string matching on the
SQL. The grant assertions are the point of the suite: they prove the
app role can write and read snapshots and can do nothing else, the
least-privilege contract ``PostgresSnapshotStore`` relies on.

``external_service`` is what makes this run: the autouse fixture in
``tests/unit/conftest.py`` hands the module the throwaway database and
the shared manager engine already retargeted at it — the same engine the
daemon's ``PostgresSnapshotStore`` uses, platform DB proxy included. Per
that conftest's rule, a missing Postgres is an error here, not a skip:
the DB-backed CI job exists to run this file.
"""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

pytestmark = pytest.mark.external_service

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "infra"
    / "database"
    / "init"
    / "40_cep_snapshots.sql"
)

_ENSURE_APP_ROLE = (
    "DO $role$ BEGIN "
    "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vigil_app') "
    "THEN CREATE ROLE vigil_app NOLOGIN; END IF; "
    "END $role$;"
)


@pytest.fixture()
def migrated_db(request):
    """Migration 40 applied to a clean slate, on the house engine.

    The vigil_app role is created when the throwaway database's server
    lacks it — CI's service user is a superuser, which is exactly the
    position init SQL runs from in provisioning.
    """
    from core.storage.connection import get_db_manager

    request.getfixturevalue("throwaway_database")
    conn = get_db_manager().engine.connect()
    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
    conn.execute(text(_ENSURE_APP_ROLE))
    conn.execute(text("DROP TABLE IF EXISTS cep_snapshots"))
    conn.execute(text("DROP FUNCTION IF EXISTS prune_cep_snapshots(interval)"))
    conn.exec_driver_sql(MIGRATION_PATH.read_text())
    try:
        yield conn
    finally:
        conn.execute(text("DROP TABLE IF EXISTS cep_snapshots"))
        conn.execute(text("DROP FUNCTION IF EXISTS prune_cep_snapshots(interval)"))
        conn.close()


def _column(conn, name: str) -> dict:
    row = conn.execute(
        text(
            "SELECT data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_name = 'cep_snapshots' AND column_name = :name"
        ),
        {"name": name},
    ).one()
    return {"data_type": row[0], "nullable": row[1] == "YES", "default": row[2]}


def test_migration_applies_twice_idempotently(migrated_db):
    conn = migrated_db
    conn.exec_driver_sql(MIGRATION_PATH.read_text())  # re-run: no-op, not a crash


def test_table_columns_match_the_contract(migrated_db):
    conn = migrated_db

    id_col = _column(conn, "id")
    assert id_col["data_type"] == "bigint"
    assert not id_col["nullable"]
    assert id_col["default"].startswith("nextval")  # bigserial, not a plain int

    created = _column(conn, "created_at")
    assert created["data_type"] == "timestamp with time zone"
    assert not created["nullable"]
    assert "now()" in created["default"]

    assert _column(conn, "engine_version")["data_type"] == "integer"
    assert _column(conn, "payload")["data_type"] == "jsonb"
    for name in ("engine_version", "payload"):
        assert not _column(conn, name)["nullable"], name


def test_created_at_index_exists(migrated_db):
    conn = migrated_db
    row = conn.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'idx_cep_snapshots_created'"
        )
    ).one_or_none()
    assert row is not None, "the restore query's access path is missing"
    assert "cep_snapshots" in row[0]


def test_app_role_grants_are_insert_select_only(migrated_db):
    """The whole least-privilege contract in one test: the app role writes
    and reads snapshots; every mutating verb is denied, so neither a
    corrupted engine nor a compromised app login can rewrite or erase its
    own recovery point."""
    conn = migrated_db
    for verb, allowed in (
        ("SELECT", True),
        ("INSERT", True),
        ("UPDATE", False),
        ("DELETE", False),
        ("TRUNCATE", False),
    ):
        granted = conn.execute(
            text("SELECT has_table_privilege('vigil_app', 'cep_snapshots', :v)"),
            {"v": verb},
        ).scalar_one()
        assert granted is allowed, verb

    # the bigserial's sequence: the INSERT path needs it, nothing else
    for priv, allowed in (("USAGE", True), ("SELECT", True), ("UPDATE", False)):
        granted = conn.execute(
            text(
                "SELECT has_sequence_privilege("
                "'vigil_app', 'cep_snapshots_id_seq', :p)"
            ),
            {"p": priv},
        ).scalar_one()
        assert granted is allowed, priv


def test_app_role_can_insert_and_read_a_roundtrip_row(migrated_db):
    """The grant set is usable: the daemon's actual INSERT/SELECT path
    works under vigil_app — a grant that exists but cannot be exercised
    would fail at the first snapshot."""
    conn = migrated_db
    try:
        conn.execute(text("SET ROLE vigil_app"))
        conn.execute(
            text(
                "INSERT INTO cep_snapshots (engine_version, payload) "
                "VALUES (1, :payload)"
            ),
            {"payload": '{"engine_version": 1, "graph": {"version": 1}}'},
        )
        row = conn.execute(
            text(
                "SELECT engine_version, payload FROM cep_snapshots "
                "ORDER BY created_at DESC, id DESC LIMIT 1"
            )
        ).one()
        assert row[0] == 1
        assert row[1]["graph"]["version"] == 1  # jsonb, parsed — not text

        # and the app role cannot prune its own rows directly
        with pytest.raises(ProgrammingError) as excinfo:
            conn.execute(text("DELETE FROM cep_snapshots"))
        assert excinfo.value.orig.pgcode == "42501"  # insufficient_privilege
    finally:
        conn.execute(text("RESET ROLE"))


def test_prune_function_removes_only_rows_past_the_age(migrated_db):
    conn = migrated_db
    conn.execute(
        text(
            "INSERT INTO cep_snapshots (engine_version, payload, created_at) "
            "VALUES (1, '{}', now() - interval '2 hours')"
        )
    )
    conn.execute(
        text("INSERT INTO cep_snapshots (engine_version, payload) VALUES (1, '{}')")
    )

    pruned = conn.execute(text("SELECT prune_cep_snapshots('1 hour')")).scalar_one()
    assert pruned == 1

    assert conn.execute(text("SELECT count(*) FROM cep_snapshots")).scalar_one() == 1
    stale = conn.execute(
        text(
            "SELECT count(*) FROM cep_snapshots "
            "WHERE created_at < now() - '1 hour'::interval"
        )
    ).scalar_one()
    assert stale == 0


def test_prune_function_is_executable_by_the_app_role_only(migrated_db):
    conn = migrated_db
    for role, allowed in (("vigil_app", True), ("public", False)):
        granted = conn.execute(
            text(
                "SELECT has_function_privilege("
                ":role, 'prune_cep_snapshots(interval)', 'EXECUTE')"
            ),
            {"role": role},
        ).scalar_one()
        assert granted is allowed, role  # PUBLIC's default EXECUTE is revoked


def test_server_stamp_and_jsonb_roundtrip(migrated_db):
    conn = migrated_db
    conn.execute(
        text(
            "INSERT INTO cep_snapshots (engine_version, payload) "
            'VALUES (1, \'{"graph": {"nodes": [], "edges": []}}\')'
        )
    )
    created_at, payload = conn.execute(
        text("SELECT created_at, payload FROM cep_snapshots LIMIT 1")
    ).one()
    assert created_at.tzinfo is not None  # TIMESTAMPTZ, stamped by the server
    assert payload["graph"]["nodes"] == []  # jsonb parses back to a dict
