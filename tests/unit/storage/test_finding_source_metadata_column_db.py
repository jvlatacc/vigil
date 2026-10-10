"""The source_metadata provenance column, in a real Postgres.

What create_all builds on a fresh database, the gap schema_report() names on
a database built before the column existed, and the step in
``scripts/migrate_schema.py`` that closes it. Each change runs inside a
transaction that is rolled back, so the shared database is left as found.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from core.storage.connection import get_db_manager

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]

MIGRATE_SCHEMA = Path(__file__).resolve().parents[3] / "scripts" / "migrate_schema.py"

COLUMN = "source_metadata"


def _column_type(conn):
    return conn.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'findings' "
            "AND column_name = :name"
        ),
        {"name": COLUMN},
    ).scalar_one_or_none()


def _step():
    # scripts/ is not a package; the migrator is a CLI file, so load it by path.
    spec = importlib.util.spec_from_file_location(
        "vigil_migrate_schema", MIGRATE_SCHEMA
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.add_findings_source_metadata


def test_create_all_builds_the_source_metadata_column():
    with get_db_manager().engine.connect() as conn:
        assert _column_type(conn) == "jsonb"


def test_migration_adds_the_column_once():
    step = _step()
    with get_db_manager().engine.connect() as conn:
        tx = conn.begin()
        try:
            # The existing-install shape: the table there, the column missing.
            conn.execute(text(f"ALTER TABLE findings DROP COLUMN {COLUMN}"))
            assert _column_type(conn) is None

            step(conn)
            assert _column_type(conn) == "jsonb"

            # A second run finds the column and leaves it.
            step(conn)
            assert _column_type(conn) == "jsonb"
        finally:
            tx.rollback()


def test_schema_report_is_ok_once_the_step_has_run():
    # schema_report() inspects on its own connection, so the drop has to
    # commit to be visible to it; the throwaway database is dropped after
    # the session either way, and the step re-adds the column it dropped.
    manager = get_db_manager()
    with manager.engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE findings DROP COLUMN IF EXISTS {COLUMN}"))

    report = manager.schema_report()
    assert report["missing_columns"].get("findings") == [COLUMN]

    step = _step()
    with manager.engine.begin() as conn:
        step(conn)
        step(conn)

    report = manager.schema_report()
    assert report["state"] == "ok"
    assert COLUMN not in report["missing_columns"].get("findings", [])
