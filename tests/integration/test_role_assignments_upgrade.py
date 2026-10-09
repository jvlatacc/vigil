"""The role_assignments upgrade path — a database that predates the table.

``tests/integration/test_schema_drift_upgrade.py`` pins what happens when a
model moves ahead of its column and nothing upgrades it. This module covers the
other half of the ritual for ``role_assignments``: an existing deployment one
release behind gets the table from the numbered SQL
(``infra/database/init/40_role_assignments.sql``), not from ``create_all``,
which never alters a running schema. What must hold after that upgrade:

* the table exists with the columns, composite key, and foreign keys the model
  declares — including ``ON DELETE CASCADE`` for users, which is what keeps a
  deleted account from leaving orphaned grants behind;
* data written before the upgrade (users, roles) survives it;
* running the file twice is harmless — the chart re-executes it on every boot;
* authorization reads and writes the table through the ORM afterwards, so the
  union walk works on the upgraded schema exactly as on a fresh install.

The fixtures CREATE and DROP a scratch database on whatever the POSTGRES_*
variables point at, so they refuse to run against a non-local host — except
under CI, where a missing service is a provisioning failure.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.orm import Session

from core.storage.models import Base, Role, RoleAssignment, User

pytestmark = [pytest.mark.integration, pytest.mark.database]

SCRATCH_DB = "vigil_test_role_assignments_upgrade"
MIGRATION = (
    Path(__file__).resolve().parents[2] / "infra/database/init/40_role_assignments.sql"
)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "0.0.0.0"}
_CONNECT_ARGS = {"connect_timeout": 5}


def _url(database: str) -> str:
    """DSN from the POSTGRES_* variables CI sets, else the compose defaults."""
    user = os.getenv("POSTGRES_USER", "deeptempo")
    password = os.getenv("POSTGRES_PASSWORD", "deeptempo_secure_password_change_me")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


def _admin_engine():
    return create_engine(
        _url("postgres"), isolation_level="AUTOCOMMIT", connect_args=_CONNECT_ARGS
    )


def _unavailable_reason():
    host = os.getenv("POSTGRES_HOST", "localhost")
    if host not in _LOCAL_HOSTS:
        return f"refusing to CREATE/DROP a database on non-local POSTGRES_HOST {host!r}"
    try:
        with _admin_engine().connect():
            pass
    except Exception as e:  # noqa: BLE001
        return f"requires a local PostgreSQL (docker compose up -d postgres): {e}"
    return None


def _schema_without_role_assignments() -> MetaData:
    """Base.metadata as the previous release knew it: no role_assignments."""
    previous = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name != "role_assignments":
            table.tometadata(previous)
    return previous


@pytest.fixture(scope="module")
def version_n_database():
    """A freshly provisioned database at 'version N' — everything but the table."""
    reason = _unavailable_reason()
    if reason:
        if os.getenv("CI"):
            pytest.fail(f"CI must run the upgrade proof: {reason}")
        pytest.skip(reason)

    admin = _admin_engine()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))

    scratch = create_engine(_url(SCRATCH_DB), connect_args=_CONNECT_ARGS)
    with scratch.connect() as c:
        # create_all cannot provision from a bare database on its own: the
        # findings GIN index needs pg_trgm or it fails with
        # 'operator class gin_trgm_ops does not exist'.
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        c.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        c.commit()

    _schema_without_role_assignments().create_all(scratch)

    # What a version-N deployment holds: roles and users, no assignments.
    with Session(scratch) as s:
        s.add(
            Role(
                role_id="role-analyst",
                name="Analyst",
                description="",
                permissions={"findings.read": True, "findings.write": True},
                is_system_role=True,
            )
        )
        s.add(
            User(
                user_id="user-preupgrade",
                username="preupgrade",
                email="preupgrade@example.com",
                password_hash="$2b$12$notarealhashbutthelengthiswhatmatters00",
                full_name="Pre Upgrade",
                role_id="role-analyst",
                is_active=True,
                is_verified=True,
                mfa_enabled=False,
                login_count=0,
            )
        )
        s.commit()

    yield scratch

    scratch.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture(scope="module")
def upgraded_database(version_n_database):
    """Version N with the numbered migration applied — the boot upgrade step."""
    scratch = version_n_database
    with scratch.connect() as c:
        c.execute(text(MIGRATION.read_text()))
        c.commit()
    return scratch


def test_the_numbered_migration_builds_the_table(upgraded_database):
    columns = {
        c["name"] for c in inspect(upgraded_database).get_columns("role_assignments")
    }
    assert columns == {"user_id", "role_id", "granted_by", "granted_at"}


def test_the_composite_key_and_foreign_keys_came_along(upgraded_database):
    inspector = inspect(upgraded_database)
    pk = inspector.get_pk_constraint("role_assignments")["constrained_columns"]
    assert pk == ["user_id", "role_id"]

    fks = {
        fk["referred_table"]: fk
        for fk in inspector.get_foreign_keys("role_assignments")
    }
    assert fks["users"]["constrained_columns"] == ["user_id"]
    assert fks["users"]["options"].get("ondelete") == "CASCADE"
    assert fks["roles"]["constrained_columns"] == ["role_id"]
    # No cascade on roles: deleting a role that still has holders is the FK's
    # job to name, not to silently permit.
    assert fks["roles"]["options"].get("ondelete") is None


def test_rerunning_the_migration_is_harmless(version_n_database):
    """The chart executes every numbered file on boot; IF NOT EXISTS must hold."""
    with version_n_database.connect() as c:
        c.execute(text(MIGRATION.read_text()))
        c.execute(text(MIGRATION.read_text()))  # second boot, same file
        c.commit()

    with version_n_database.connect() as c:
        count = c.execute(text("SELECT count(*) FROM role_assignments")).scalar()
    assert count == 0


def test_pre_upgrade_rows_survive_and_authorization_reads_the_table(upgraded_database):
    """Users and roles from before the upgrade keep working through the ORM."""
    with Session(upgraded_database) as session:
        user = session.query(User).filter_by(user_id="user-preupgrade").one()
        role = session.query(Role).filter_by(role_id="role-analyst").one()
        session.add(
            RoleAssignment(
                user_id=user.user_id, role_id=role.role_id, granted_by="admin"
            )
        )
        session.commit()

        assigned = [
            row[0]
            for row in session.query(RoleAssignment.role_id).filter(
                RoleAssignment.user_id == "user-preupgrade"
            )
        ]
    assert assigned == ["role-analyst"]
