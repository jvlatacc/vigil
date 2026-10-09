"""The run's stamped initiator, resolved against a real database.

A headless run's tool dispatch is authorized against the person stamped on the
run's row at start (``triggered_by``), so the lookup is the thing that decides
who a run acts as. ``WorkflowRunService.initiator`` must return that person's
username only when the stamp names an active user of this instance: system
starters ("orchestrator", a handoff's join key) name no user, and those runs
act as the system rather than as a person.

The database is a scratch one created here, the shared ``DatabaseManager``
retargeted at it for the module and restored afterwards -- the pattern of
``test_first_admin_bootstrap.py``. Skips when no local Postgres answers,
except under ``CI``, where a missing service is a provisioning failure.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from core.storage.connection import DatabaseConfig, get_db_manager
from core.storage.models import Base, Role, User, WorkflowRun

pytestmark = [pytest.mark.integration, pytest.mark.database]

SCRATCH_DB = "vigil_test_run_initiator"

# These fixtures CREATE/DROP DATABASE; only ever against a loopback host.
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


@pytest.fixture(scope="module")
def scratch_database():
    reason = _unavailable_reason()
    if reason:
        if os.getenv("CI"):
            pytest.fail(f"CI must run the initiator lookup: {reason}")
        pytest.skip(reason)

    admin = _admin_engine()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))

    scratch = create_engine(_url(SCRATCH_DB), connect_args=_CONNECT_ARGS)
    with scratch.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        c.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
    Base.metadata.create_all(scratch)
    with Session(scratch) as s:
        s.add(
            Role(
                role_id="role-viewer",
                name="Viewer",
                description="Read-only",
                permissions={"findings.read": True},
                is_system_role=True,
            )
        )
        s.add(
            User(
                user_id="user-active",
                username="nestor",
                email="nestor@example.com",
                password_hash="not-a-real-hash",
                full_name="Nestor",
                role_id="role-viewer",
                is_active=True,
            )
        )
        s.add(
            User(
                user_id="user-inactive",
                username="sidelined",
                email="sidelined@example.com",
                password_hash="not-a-real-hash",
                full_name="Sidelined",
                role_id="role-viewer",
                is_active=False,
            )
        )
        s.commit()
    scratch.dispose()

    manager = get_db_manager()
    manager.retarget(DatabaseConfig(connection_string=_url(SCRATCH_DB)))
    assert manager.config.database == SCRATCH_DB
    try:
        yield
    finally:
        manager.retarget(DatabaseConfig(), validate=False)
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        admin.dispose()


def _run(triggered_by: str | None) -> str:
    """A run row stamped with ``triggered_by``, through the real begin_run."""
    from core.workflows.workflow_run_service import WorkflowRunService

    run_id = f"run-initiator-{os.urandom(6).hex()}"
    WorkflowRunService().begin_run(
        workflow_id="threat-hunt",
        workflow_name="threat-hunt",
        workflow_source="agent",
        triggered_by=triggered_by or "",
        run_id=run_id,
    )
    return run_id


def _raw_run(triggered_by: str | None) -> str:
    """A run row written directly, for stamps begin_run would not take."""
    run_id = f"run-initiator-{os.urandom(6).hex()}"
    manager = get_db_manager()
    with manager.session_scope() as session:
        session.add(
            WorkflowRun(
                run_id=run_id,
                workflow_id="threat-hunt",
                workflow_name="threat-hunt",
                workflow_source="agent",
                status="queued",
                triggered_by=triggered_by,
            )
        )
    return run_id


def test_an_active_users_stamp_resolves_to_them(scratch_database):
    from core.workflows.workflow_run_service import WorkflowRunService

    assert WorkflowRunService().initiator(_run("nestor")) == "nestor"


def test_an_inactive_user_is_not_the_run_initiator(scratch_database):
    # A disabled account cannot hold a dispatch permission, so its stamp must
    # not authorize a run either.
    from core.workflows.workflow_run_service import WorkflowRunService

    assert WorkflowRunService().initiator(_run("sidelined")) is None


def test_a_system_start_names_no_user(scratch_database):
    # The orchestrator's schedules stamp a sentinel, not a username; a run row
    # that names no user of this instance has nobody to authorize against.
    from core.workflows.workflow_run_service import WorkflowRunService

    assert WorkflowRunService().initiator(_run("orchestrator")) is None


def test_an_unstamped_run_has_no_initiator(scratch_database):
    from core.workflows.workflow_run_service import WorkflowRunService

    assert WorkflowRunService().initiator(_raw_run(None)) is None


def test_an_unknown_run_has_no_initiator(scratch_database):
    from core.workflows.workflow_run_service import WorkflowRunService

    assert WorkflowRunService().initiator("no-such-run") is None
