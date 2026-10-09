"""The digital-twin tables against Postgres.

The round-trips the no-DB contract tests in ``test_twin_models.py`` cannot
see: rows survive the commit, the natural-key uniques and the layer check
constraint are refused by the server, deleting a device takes its processes
and connections with it while deleting a process demotes its connection to
device level, the drift report calls the tables ok, and
``scripts/migrate_schema.py`` carries a database to the same shape — twice,
cleanly, and again after the tables are dropped to simulate an upgrade.

Round-trips run on the throwaway database tests/unit/conftest.py provisions
per process. The migrate-script step provisions its own scratch database:
the script runs its whole step list, and its seed must not leak into the
shared throwaway other suites read.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from core.storage.connection import DatabaseConfig, get_db_manager
from core.storage.models import TwinConnection, TwinDevice, TwinProcess
from core.storage.unit_of_work import unit_of_work
from scripts.migrate_schema import run_migrations

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]

_TWIN_TABLES = {"twin_devices", "twin_processes", "twin_connections"}
_TWIN_INDEXES = {
    "uniq_twin_devices_device_key",
    "idx_twin_devices_ip_address",
    "idx_twin_devices_mac_address",
    "idx_twin_devices_serial_number",
    "uniq_twin_processes_process_key",
    "idx_twin_processes_device_pid",
    "uniq_twin_connections_connection_key",
    "idx_twin_connections_device_type",
    "idx_twin_connections_remote_ip",
}


@pytest.fixture(autouse=True)
def _clean():
    with unit_of_work() as session:
        session.query(TwinConnection).delete()
        session.query(TwinProcess).delete()
        session.query(TwinDevice).delete()
    yield
    with unit_of_work() as session:
        session.query(TwinConnection).delete()
        session.query(TwinProcess).delete()
        session.query(TwinDevice).delete()


def _add_device(**kw):
    row = TwinDevice(
        device_key=kw.pop("device_key", "host:web-01"),
        source=kw.pop("source", "seed"),
        **kw,
    )
    with unit_of_work() as session:
        session.add(row)
    return row


def _add_process(device_row, **kw):
    row = TwinProcess(
        process_key=kw.pop("process_key", "host:web-01:1204:nginx"),
        device_id=device_row.id,
        pid=kw.pop("pid", 1204),
        name=kw.pop("name", "nginx"),
        source=kw.pop("source", "seed"),
        **kw,
    )
    with unit_of_work() as session:
        session.add(row)
    return row


def _add_connection(device_row, process_row=None, **kw):
    row = TwinConnection(
        connection_key=kw.pop(
            "connection_key", "socket:tcp:10.0.4.11:443:10.0.4.17:52341"
        ),
        device_id=device_row.id,
        process_id=process_row.id if process_row else None,
        connection_type=kw.pop("connection_type", "socket"),
        source=kw.pop("source", "seed"),
        **kw,
    )
    with unit_of_work() as session:
        session.add(row)
    return row


def _fetch(model, **filters):
    with unit_of_work() as session:
        rows = session.scalars(select(model).filter_by(**filters)).all()
        # Detach so the assertions read what Postgres holds, not the cache.
        session.expunge_all()
    return rows


# --- round-trips --------------------------------------------------------------


def test_a_device_round_trips_through_postgres():
    _add_device(
        hostname="web-01",
        ip_address="10.0.4.11",
        mac_address="0a:1b:2c:3d:4e:01",
        serial_number="C02X1234ABCD",
        device_type="server",
        os_info="Ubuntu 24.04",
        attributes={"rack": "r14"},
    )
    (row,) = _fetch(TwinDevice, device_key="host:web-01")
    assert row.hostname == "web-01"
    assert row.ip_address == "10.0.4.11"
    assert row.mac_address == "0a:1b:2c:3d:4e:01"
    assert row.serial_number == "C02X1234ABCD"
    assert row.device_type == "server"
    assert row.os_info == "Ubuntu 24.04"
    assert row.attributes == {"rack": "r14"}


def test_insert_fills_the_defaults_the_server_owns():
    _add_device()
    (row,) = _fetch(TwinDevice, device_key="host:web-01")
    assert row.id is not None  # gen_random_uuid()
    assert row.device_type == "unknown"
    assert row.first_seen is not None
    assert row.last_seen is not None
    assert row.attributes is None


def test_two_devices_cannot_share_a_device_key():
    _add_device()
    with pytest.raises(IntegrityError):
        _add_device(hostname="an-impostor")


def test_a_process_round_trips_with_its_device():
    device = _add_device()
    _add_process(
        device,
        user="www-data",
        command="nginx: worker",
        started_at=datetime(2026, 10, 9, 20, 0, 0),
    )
    (row,) = _fetch(TwinProcess, process_key="host:web-01:1204:nginx")
    assert row.device_id == device.id
    assert row.pid == 1204
    assert row.name == "nginx"
    assert row.user == "www-data"
    assert row.command == "nginx: worker"
    assert row.started_at is not None


def test_two_processes_cannot_share_a_process_key():
    device = _add_device()
    _add_process(device)
    with pytest.raises(IntegrityError):
        _add_process(device, pid=1205, name="sshd")


def test_a_connection_round_trips_with_its_process():
    device = _add_device()
    process = _add_process(device)
    _add_connection(
        device,
        process,
        protocol="tcp",
        local_ip="10.0.4.11",
        local_port=443,
        remote_ip="10.0.4.17",
        remote_port=52341,
        state="established",
        direction="inbound",
    )
    (row,) = _fetch(
        TwinConnection, connection_key="socket:tcp:10.0.4.11:443:10.0.4.17:52341"
    )
    assert row.device_id == device.id
    assert row.process_id == process.id
    assert row.connection_type == "socket"
    assert (row.local_ip, row.local_port) == ("10.0.4.11", 443)
    assert (row.remote_ip, row.remote_port) == ("10.0.4.17", 52341)
    assert (row.state, row.direction) == ("established", "inbound")


def test_a_device_level_connection_needs_no_process():
    device = _add_device()
    _add_connection(device)
    (row,) = _fetch(
        TwinConnection, connection_key="socket:tcp:10.0.4.11:443:10.0.4.17:52341"
    )
    assert row.process_id is None
    assert row.device_id == device.id


def test_two_connections_cannot_share_a_connection_key():
    device = _add_device()
    _add_connection(device)
    with pytest.raises(IntegrityError):
        _add_connection(device, remote_port=59999)


def test_a_connection_type_outside_the_enum_is_refused():
    device = _add_device()
    with pytest.raises(IntegrityError):
        _add_connection(device, connection_type="beacon")


# --- delete semantics ---------------------------------------------------------


def test_deleting_a_device_takes_its_processes_and_connections():
    device = _add_device()
    process = _add_process(device)
    _add_connection(device, process)

    with unit_of_work() as session:
        session.delete(session.get(TwinDevice, device.id))

    assert _fetch(TwinDevice, device_key="host:web-01") == []
    assert _fetch(TwinProcess) == []
    assert _fetch(TwinConnection) == []


def test_deleting_a_process_demotes_its_connection_to_device_level():
    device = _add_device()
    process = _add_process(device)
    _add_connection(device, process)

    with unit_of_work() as session:
        session.delete(session.get(TwinProcess, process.id))

    rows = _fetch(TwinConnection)
    assert len(rows) == 1  # the observed flow is kept
    assert rows[0].process_id is None
    assert rows[0].device_id == device.id


# --- drift report -------------------------------------------------------------


def test_the_drift_report_calls_the_twin_tables_ok():
    # The throwaway database is built by create_all from Base.metadata, so a
    # twin table the model declares but Postgres lacks (or a column whose
    # nullability disagrees) shows up here as drift instead of ok.
    report = get_db_manager().schema_report()
    assert report["state"] == "ok"
    assert not _TWIN_TABLES & set(report["missing_tables"])
    assert not _TWIN_TABLES & set(report["missing_columns"])


# --- the migrate-script path --------------------------------------------------


def _scratch_url(database: str) -> str:
    """Build a DSN from the POSTGRES_* variables, else dev compose defaults.

    The driver is pinned to psycopg2 the way the app pins it
    (core/storage/connection.py) — on SQLAlchemy 2.1 a bare
    ``postgresql://`` resolves to the psycopg (v3) dialect, which is not a
    repo dependency.
    """
    user = os.getenv("POSTGRES_USER", "deeptempo")
    password = os.getenv("POSTGRES_PASSWORD", "deeptempo_secure_password_change_me")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


@pytest.fixture
def _migrate_url(request):
    """A scratch database standing in for an existing deployment.

    Same shape as the conftest throwaway and the integration fixtures: a
    random name on whatever POSTGRES_* points at, dropped with FORCE. The
    full model schema is create_all'd first — the integration fixture does
    the same, because the script's early index steps assume the tables are
    already there (only the later create_missing_tables step builds from
    bare metadata) — then the script's whole step list runs against it.
    """
    from core.storage.models.base import Base

    manager = get_db_manager()
    name = f"vigil_test_twin_migrate_{os.getpid()}_{secrets.token_hex(4)}"
    ident = '"' + name.replace('"', '""') + '"'
    with manager.engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(f"CREATE DATABASE {ident}"))

    url = _scratch_url(name)
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            for statement in (
                "CREATE EXTENSION IF NOT EXISTS pg_trgm",
                'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"',
            ):
                try:
                    conn.execute(text(statement))
                except Exception:  # noqa: BLE001 — same tolerance as conftest
                    pass
        # The baseline schema an existing deployment carries.
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    def _drop():
        try:
            with manager.engine.connect() as conn:
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text(f"DROP DATABASE IF EXISTS {ident} WITH (FORCE)"))
        except Exception as e:  # noqa: BLE001
            print(f"[test-db] could not drop {name}, clean it up by hand: {e}")

    request.addfinalizer(_drop)
    return url


def _twin_shapes(engine):
    """The twin tables and index names a database currently holds."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename LIKE 'twin_%'")
            )
        }
    return tables, names


def test_migrate_schema_builds_the_twin_tables_and_runs_twice_cleanly(_migrate_url):
    url = _migrate_url
    first = run_migrations(url=url)
    assert first["failed"] == []

    engine = create_engine(url)
    try:
        tables, indexes = _twin_shapes(engine)
        assert _TWIN_TABLES <= tables
        assert _TWIN_INDEXES <= indexes
    finally:
        engine.dispose()

    # The twice-cleanly run: every step applies again, nothing fails, and
    # the shape is unchanged.
    second = run_migrations(url=url)
    assert second["failed"] == []
    assert len(second["applied"]) == len(first["applied"])

    # The upgrade path this step exists for: a database the twin predates.
    # Drop the three tables and let the script carry the database forward.
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(
                text(
                    "DROP TABLE IF EXISTS twin_connections, twin_processes,"
                    " twin_devices CASCADE"
                )
            )
        tables, _ = _twin_shapes(engine)
        assert not _TWIN_TABLES & tables
    finally:
        engine.dispose()

    third = run_migrations(url=url)
    assert third["failed"] == []

    engine = create_engine(url)
    try:
        tables, indexes = _twin_shapes(engine)
        assert _TWIN_TABLES <= tables
        assert _TWIN_INDEXES <= indexes
    finally:
        engine.dispose()


def test_the_migrated_schema_reports_ok(_migrate_url):
    """A database the script carried forward passes the startup drift check.

    Not just the create_all path: schema_report() is what a booting backend
    runs, and the script is what an upgraded database runs — the two must
    agree.
    """
    url = _migrate_url
    assert run_migrations(url=url)["failed"] == []

    manager = get_db_manager()
    config = DatabaseConfig()
    config.database = url.rsplit("/", 1)[1]
    manager.retarget(config)
    report = manager.schema_report()
    assert report["state"] == "ok"
    assert not _TWIN_TABLES & set(report["missing_tables"])
