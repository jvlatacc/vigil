"""The digital-twin tables' model contract, without a database.

Complement of the real-Postgres round-trip in ``test_twin_models_db.py``:
what an instance promises in memory — the columns, the natural keys, the
layer enum, the FK delete semantics — is checked here so a type or default
mistake fails in the no-service unit job, not only under CI's DB-backed
one. The DDL is compiled and inspected against the columns the SQL mirror
(``infra/database/init/42_digital_twin.sql``) declares.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from core.storage.models import TwinConnection, TwinDevice, TwinProcess
from core.storage.models.base import Base
from core.storage.models.digital_twin import TWIN_CONNECTION_TYPES

pytestmark = pytest.mark.unit

FIXED_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _ddl(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def _index_ddl(model) -> str:
    return "\n".join(
        str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in model.__table__.indexes
    )


# --- registration -------------------------------------------------------------


def test_all_three_models_register_on_the_shared_metadata():
    # The package __init__ re-exports are what keep the classes on
    # Base.metadata for create_all, the schema snapshot, and the drift
    # report.
    assert {"twin_devices", "twin_processes", "twin_connections"} <= set(
        Base.metadata.tables
    )


# --- devices ------------------------------------------------------------------


def test_a_device_row_holds_every_identity_fact():
    device = TwinDevice(
        device_key="host:web-01",
        hostname="web-01",
        ip_address="10.0.4.11",
        mac_address="0a:1b:2c:3d:4e:01",
        serial_number="C02X1234ABCD",
        device_type="server",
        os_info="Ubuntu 24.04",
        source="seed",
        attributes={"rack": "r14"},
    )
    assert device.device_key == "host:web-01"
    assert device.hostname == "web-01"
    assert device.mac_address == "0a:1b:2c:3d:4e:01"
    assert device.serial_number == "C02X1234ABCD"
    assert device.device_type == "server"
    assert device.attributes == {"rack": "r14"}


def test_a_bare_device_constructs_and_defers_defaults_to_insert():
    device = TwinDevice()
    assert device.id is None
    assert device.device_key is None
    assert device.device_type is None  # applied at INSERT, not construction
    assert device.attributes is None


def test_the_device_table_declares_the_expected_columns():
    columns = {c.key for c in sa_inspect(TwinDevice).mapper.column_attrs}
    assert columns == {
        "id",
        "device_key",
        "hostname",
        "ip_address",
        "mac_address",
        "serial_number",
        "device_type",
        "os_info",
        "source",
        "first_seen",
        "last_seen",
        "attributes",
    }


def test_device_type_defaults_unknown_in_code_and_in_the_database():
    device_type = TwinDevice.__table__.c.device_type
    assert device_type.default.arg == "unknown"
    assert device_type.server_default.arg == "unknown"


def test_last_seen_bumps_on_every_write():
    last_seen = TwinDevice.__table__.c.last_seen
    assert last_seen.onupdate is not None
    assert last_seen.server_default is not None


def test_the_device_keys_are_indexed_for_identity_lookups():
    ddl = _index_ddl(TwinDevice)
    assert "CREATE UNIQUE INDEX uniq_twin_devices_device_key" in ddl
    assert "CREATE INDEX idx_twin_devices_ip_address" in ddl
    assert "CREATE INDEX idx_twin_devices_mac_address" in ddl
    assert "CREATE INDEX idx_twin_devices_serial_number" in ddl


# --- processes ----------------------------------------------------------------


def test_a_process_row_holds_who_ran_what():
    process = TwinProcess(
        process_key="host:web-01:1204:nginx",
        device_id=FIXED_UUID,
        pid=1204,
        name="nginx",
        user="www-data",
        command="nginx: worker",
        source="seed",
    )
    assert process.process_key == "host:web-01:1204:nginx"
    assert process.pid == 1204
    assert process.name == "nginx"
    assert process.user == "www-data"
    assert process.command == "nginx: worker"


def test_the_process_table_declares_the_expected_columns():
    columns = {c.key for c in sa_inspect(TwinProcess).mapper.column_attrs}
    assert columns == {
        "id",
        "process_key",
        "device_id",
        "pid",
        "name",
        "user",
        "command",
        "started_at",
        "source",
        "first_seen",
        "last_seen",
        "attributes",
    }


def test_a_process_belongs_to_its_device_and_goes_with_it():
    device_id = TwinProcess.__table__.c.device_id
    fk = next(f for f in device_id.foreign_keys)
    assert fk.column.table.name == "twin_devices"
    assert fk.ondelete == "CASCADE"
    assert device_id.nullable is False


def test_the_process_index_leads_with_the_device():
    ddl = _index_ddl(TwinProcess)
    assert "CREATE UNIQUE INDEX uniq_twin_processes_process_key" in ddl
    assert "CREATE INDEX idx_twin_processes_device_pid" in ddl
    assert "(device_id, pid)" in ddl


# --- connections --------------------------------------------------------------


def test_a_connection_row_holds_the_five_tuple_and_its_layer_class():
    connection = TwinConnection(
        connection_key="socket:tcp:10.0.4.11:443:10.0.4.17:52341",
        device_id=FIXED_UUID,
        connection_type="socket",
        protocol="tcp",
        local_ip="10.0.4.11",
        local_port=443,
        remote_ip="10.0.4.17",
        remote_port=52341,
        state="established",
        direction="inbound",
        source="seed",
    )
    assert connection.connection_key.endswith(":52341")
    assert connection.connection_type == "socket"
    assert (connection.local_ip, connection.local_port) == ("10.0.4.11", 443)
    assert (connection.remote_ip, connection.remote_port) == ("10.0.4.17", 52341)
    assert (connection.state, connection.direction) == ("established", "inbound")


def test_the_connection_table_declares_the_expected_columns():
    columns = {c.key for c in sa_inspect(TwinConnection).mapper.column_attrs}
    assert columns == {
        "id",
        "connection_key",
        "device_id",
        "process_id",
        "connection_type",
        "protocol",
        "local_ip",
        "local_port",
        "remote_ip",
        "remote_port",
        "state",
        "direction",
        "source",
        "started_at",
        "first_seen",
        "last_seen",
        "attributes",
    }


def test_connection_type_is_constrained_to_the_three_layer_classes():
    ddl = _ddl(TwinConnection)
    assert "ck_twin_connections_connection_type" in ddl
    assert "connection_type IN ('socket', 'stream', 'session')" in ddl
    # One source of truth: the check constraint and the exported tuple must
    # agree, so the ingest API's Pydantic Literal cannot drift from the DDL.
    assert tuple(TWIN_CONNECTION_TYPES) == ("socket", "stream", "session")


def test_a_connection_dies_with_its_device_but_outlives_its_process():
    table = TwinConnection.__table__
    device_fk = next(f for f in table.c.device_id.foreign_keys)
    process_fk = next(f for f in table.c.process_id.foreign_keys)
    assert device_fk.ondelete == "CASCADE"
    assert table.c.device_id.nullable is False
    assert process_fk.ondelete == "SET NULL"
    # Nullable: a network sensor reports device-level traffic it cannot
    # attribute to a PID.
    assert table.c.process_id.nullable is True


def test_the_connection_indexes_serve_the_graphs_pivots():
    ddl = _index_ddl(TwinConnection)
    assert "CREATE UNIQUE INDEX uniq_twin_connections_connection_key" in ddl
    assert "CREATE INDEX idx_twin_connections_device_type" in ddl
    assert "(device_id, connection_type)" in ddl
    assert "CREATE INDEX idx_twin_connections_remote_ip" in ddl
