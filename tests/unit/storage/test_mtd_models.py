"""The MTD tables' model contract, without a database.

Complement of the real-Postgres round-trip in ``test_mtd_models_db.py``:
what an instance promises in memory — the columns, the defaults, the
status/removal pairing — is checked here so a type or default mistake fails
in the no-service unit job, not only under CI's DB-backed one. The DDL is
compiled and inspected against the columns the SQL mirror declares.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from core.storage.models import MtdDecoyRegistry, MtdIpExclusion

pytestmark = pytest.mark.unit

FIXED_DT = datetime(2026, 10, 9, 20, 31, 2, tzinfo=timezone.utc)


def _ddl(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


# --- the decoy registry -------------------------------------------------------


def test_a_decoy_row_holds_every_routing_fact():
    decoy = MtdDecoyRegistry(
        decoy_id="decoy-0123456789abcdef",
        name="ssh-decoy-01",
        kind="ssh",
        endpoint="ssh-decoy-01:2222",
        canary_credential_ref="honey_router.canary.ssh-decoy-01",
        rotated_at=FIXED_DT,
    )
    assert decoy.decoy_id == "decoy-0123456789abcdef"
    assert (decoy.name, decoy.kind, decoy.endpoint) == (
        "ssh-decoy-01",
        "ssh",
        "ssh-decoy-01:2222",
    )
    assert decoy.canary_credential_ref == "honey_router.canary.ssh-decoy-01"
    assert decoy.rotated_at == FIXED_DT


def test_a_bare_decoy_constructs_and_defers_defaults_to_insert():
    decoy = MtdDecoyRegistry()
    assert decoy.decoy_id is None
    assert decoy.rotated_at is None


def test_the_registry_table_declares_the_expected_columns():
    columns = {c.key for c in sa_inspect(MtdDecoyRegistry).mapper.column_attrs}
    assert columns == {
        "decoy_id",
        "name",
        "kind",
        "endpoint",
        "status",
        "canary_credential_ref",
        "rotated_at",
        "created_at",
        "updated_at",
    }


def test_status_defaults_active_in_code_and_in_the_database():
    status = MtdDecoyRegistry.__table__.c.status
    assert status.default.arg == "active"
    assert status.server_default.arg == "active"


def test_updated_at_bumps_on_every_write():
    updated_at = MtdDecoyRegistry.__table__.c.updated_at
    assert updated_at.onupdate is not None
    assert updated_at.server_default is not None


def test_registry_ddl_constrains_kind_and_status():
    ddl = _ddl(MtdDecoyRegistry)
    assert "CREATE TABLE mtd_decoy_registry" in ddl
    assert "ck_mtd_decoy_registry_kind" in ddl
    assert "kind IN ('ssh', 'http')" in ddl
    assert "ck_mtd_decoy_registry_status" in ddl
    assert "status IN ('active', 'retired')" in ddl


def test_the_registry_index_ddl():
    ddl = "\n".join(
        str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in MtdDecoyRegistry.__table__.indexes
    )
    assert "CREATE UNIQUE INDEX uniq_mtd_decoy_registry_active_name" in ddl
    assert "WHERE status = 'active'" in ddl
    assert "CREATE INDEX idx_mtd_decoy_registry_kind_status" in ddl


def test_canary_credential_ref_is_required():
    canary = MtdDecoyRegistry.__table__.c.canary_credential_ref
    assert canary.nullable is False


# --- the never-route exclusions -----------------------------------------------


def test_a_never_route_row_holds_who_why_and_when():
    row = MtdIpExclusion(
        exclusion_id="mtdexcl-0123456789ab",
        ip="203.0.113.7",
        reason="production honeypot host",
        added_by="analyst-1",
    )
    assert row.exclusion_id == "mtdexcl-0123456789ab"
    assert (row.ip, row.reason, row.added_by) == (
        "203.0.113.7",
        "production honeypot host",
        "analyst-1",
    )


def test_the_exclusion_table_declares_the_expected_columns():
    columns = {c.key for c in sa_inspect(MtdIpExclusion).mapper.column_attrs}
    assert columns == {
        "exclusion_id",
        "ip",
        "reason",
        "added_by",
        "added_at",
        "status",
        "removed_at",
        "removed_by",
    }


def test_exclusion_status_defaults_active():
    status = MtdIpExclusion.__table__.c.status
    assert status.default.arg == "active"
    assert status.server_default.arg == "active"


def test_removal_columns_are_optional_and_status_is_not():
    table = MtdIpExclusion.__table__
    assert table.c.status.nullable is False
    assert table.c.removed_at.nullable is True
    assert table.c.removed_by.nullable is True


def test_exclusion_ddl_records_the_status_transition():
    ddl = _ddl(MtdIpExclusion)
    assert "CREATE TABLE mtd_ip_exclusions" in ddl
    assert "ck_mtd_ip_exclusions_status" in ddl
    assert "status IN ('active', 'removed')" in ddl
    # Status and the removal record must agree: a 'removed' row without
    # who/when is a lie the constraint refuses.
    assert "ck_mtd_ip_exclusions_status_removal" in ddl
    assert "(status = 'active') = (removed_at IS NULL)" in ddl


def test_the_exclusion_index_ddl():
    ddl = "\n".join(
        str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in MtdIpExclusion.__table__.indexes
    )
    assert "CREATE UNIQUE INDEX uniq_mtd_ip_exclusions_active_ip" in ddl
    assert "WHERE status = 'active'" in ddl
    assert "CREATE INDEX idx_mtd_ip_exclusions_added_at" in ddl
    assert "added_at DESC" in ddl


# --- registration -------------------------------------------------------------


def test_both_models_register_on_the_shared_metadata():
    # The package __init__ re-exports are what keep the classes on
    # Base.metadata for create_all and the schema snapshot.
    assert MtdDecoyRegistry.__tablename__ in MtdDecoyRegistry.metadata.tables
    assert MtdIpExclusion.__tablename__ in MtdIpExclusion.metadata.tables
