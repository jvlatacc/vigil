"""tool_call_audit is append-only at vigil_app, and the trigger owns the hashes.

Connects as the app role for the grant assertions (not has_table_privilege),
as the ledger's test does (issue #824). The hash-chain assertions run against
real Postgres so the SQL trigger and the Python writer/verifier are caught
drifting -- the failure this pairing exists to catch.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker

from core.audit import tool_calls
from core.storage.models import ToolCallAudit

pytestmark = [pytest.mark.integration, pytest.mark.database]

REPO_ROOT = Path(__file__).resolve().parents[2]
INIT = REPO_ROOT / "infra" / "database" / "init"
SCRATCH_DB = "vigil_test_tool_call_audit_grants"
INSUFFICIENT_PRIVILEGE = "42501"


def _parts():
    return {
        "user": os.getenv("POSTGRES_USER", "deeptempo"),
        "password": os.getenv(
            "POSTGRES_PASSWORD", "deeptempo_secure_password_change_me"
        ),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
    }


def _url(database: str, user: str | None = None, password: str | None = None) -> str:
    parts = _parts()
    who = user if user is not None else parts["user"]
    pw = password if password is not None else parts["password"]
    return (
        f"postgresql+psycopg2://{quote(who, safe='')}:{quote(pw, safe='')}"
        f"@{parts['host']}:{parts['port']}/{database}"
    )


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


def _pgcode(exc: ProgrammingError) -> str | None:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "pgcode", None)


@pytest.fixture(scope="module")
def engines():
    """Owner provisions the schema and the role; tests get both engines."""
    admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))

    owner = create_engine(_url(SCRATCH_DB))
    password = _parts()["password"]
    with owner.connect() as conn:
        # agent_events first: 30's grants name it, exactly as the ledger's
        # fixture does. Then the role, then this table's DDL.
        conn.exec_driver_sql((INIT / "19_agent_ledger.sql").read_text())
        conn.exec_driver_sql((INIT / "30_vigil_app_role.sql").read_text())
        conn.exec_driver_sql((INIT / "41_tool_call_audit.sql").read_text())
        escaped = password.replace("'", "''")
        conn.exec_driver_sql(f"ALTER ROLE vigil_app PASSWORD '{escaped}'")
        conn.commit()

    app = create_engine(_url(SCRATCH_DB, user="vigil_app", password=password))
    yield owner, app

    app.dispose()
    owner.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture()
def writer_on_owner(engines, monkeypatch):
    """record_tool_call/verify_chain, pointed at the owner's scratch DB."""
    owner, _ = engines
    Session = sessionmaker(bind=owner)

    @contextmanager
    def _owner_store(_=None):
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(tool_calls, "unit_of_work", _owner_store)


def _call(**overrides):
    fields = dict(
        actor_username="ada",
        surface=tool_calls.SURFACE_AGENT,
        server_name="github",
        tool_name="github_search",
        args={"query": "x"},
        decision=tool_calls.DECISION_ALLOW,
        outcome="ok",
    )
    fields.update(overrides)
    return fields


class TestAppendOnlyGrants:
    def test_vigil_app_insert_succeeds_update_and_delete_fail(self, engines):
        _, app = engines
        with app.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO tool_call_audit "
                    "(actor_username, surface, server_name, tool_name, decision) "
                    "VALUES ('ada', 'agent', 'github', 'github_search', 'allow')"
                )
            )
            conn.commit()
            count = conn.execute(
                text("SELECT count(*) FROM tool_call_audit")
            ).scalar_one()
        assert count == 1

        with pytest.raises(ProgrammingError) as updated:
            with app.connect() as conn:
                conn.execute(
                    text(
                        "UPDATE tool_call_audit "
                        "SET outcome = 'tampered' WHERE actor_username = 'ada'"
                    )
                )
                conn.commit()
        assert _pgcode(updated.value) == INSUFFICIENT_PRIVILEGE

        with pytest.raises(ProgrammingError) as deleted:
            with app.connect() as conn:
                conn.execute(text("DELETE FROM tool_call_audit"))
                conn.commit()
        assert _pgcode(deleted.value) == INSUFFICIENT_PRIVILEGE

    def test_even_the_writer_session_cannot_rewrite_through_the_app_role(
        self, engines, monkeypatch
    ):
        """The stored row is the record; vigil_app cannot fix up history."""
        _, app = engines
        Session = sessionmaker(bind=app)

        @contextmanager
        def _app_store(_=None):
            session = Session()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        monkeypatch.setattr(tool_calls, "unit_of_work", _app_store)
        tool_calls.record_tool_call(**_call(tool_name="github_close"))
        with Session() as session:
            row_id = session.execute(
                select(ToolCallAudit.id).where(
                    ToolCallAudit.tool_name == "github_close"
                )
            ).scalar_one()
            with pytest.raises(ProgrammingError):
                session.query(ToolCallAudit).filter_by(id=row_id).update(
                    {"outcome": "edited"}
                )
                session.commit()


class TestTriggerAndWriterAgree:
    def test_the_trigger_hashes_what_the_python_verifier_expects(
        self, engines, writer_on_owner
    ):
        owner, _ = engines
        with owner.connect() as conn:
            conn.execute(text("TRUNCATE tool_call_audit"))
            conn.commit()

        for i in range(3):
            tool_calls.record_tool_call(
                **_call(tool_name=f"github_search_{i}", args={"i": i})
            )

        verdict = tool_calls.verify_chain()
        assert verdict.ok is True, verdict.broken_at
        assert verdict.checked == 3

    def test_a_row_inserted_with_a_bogus_hash_still_lands_hashed(
        self, engines, writer_on_owner
    ):
        """The trigger, not the caller, decides event_hash on a real database."""
        owner, _ = engines
        with owner.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO tool_call_audit "
                    "(actor_username, surface, server_name, tool_name, decision, "
                    " prev_hash, event_hash) "
                    "VALUES ('ada', 'agent', 'github', 'github_open', 'allow', "
                    " 'forged-prev', 'forged-hash')"
                )
            )
            conn.commit()
            stored = conn.execute(
                text(
                    "SELECT prev_hash, event_hash FROM tool_call_audit "
                    "WHERE tool_name = 'github_open'"
                )
            ).one()
        assert stored.prev_hash != "forged-prev"
        assert stored.event_hash != "forged-hash"
        assert tool_calls.verify_chain().ok is True

    def test_a_tampered_row_breaks_the_chain_where_it_was_touched(
        self, engines, writer_on_owner
    ):
        owner, _ = engines
        for i in range(3):
            tool_calls.record_tool_call(**_call(tool_name=f"github_edit_{i}"))

        with owner.connect() as conn:
            target = conn.execute(
                text(
                    "SELECT id FROM tool_call_audit " "ORDER BY id ASC OFFSET 1 LIMIT 1"
                )
            ).scalar_one()
            conn.execute(
                text("UPDATE tool_call_audit SET outcome = 'edited' WHERE id = :i"),
                {"i": target},
            )
            conn.commit()

        verdict = tool_calls.verify_chain()
        assert verdict.ok is False
        assert verdict.broken_at == target
