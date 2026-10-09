"""A scratch audit store for the integration-surface unit tests.

The dispatch surfaces these tests exercise — the outbound vendor funnel and
Vigil's own in-process tools — write a ``tool_call_audit`` row for every
call, and the write is fail-closed: a call whose row cannot land does not
answer. These tests are about the dispatch, so they get the same SQLite
stand-in the writer's own suite uses: the rows land (the fail-closed rule is
honoured, not bypassed), the responses keep the pipe contract, and the
attribution tests read the rows back out.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def audit_store(monkeypatch):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_is_integer_on_sqlite(type_, compiler, **kw):  # pragma: no cover
        return "INTEGER"

    from core.audit import tool_calls
    from core.storage.models import ToolCallAudit
    from core.storage.models.base import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[ToolCallAudit.__table__])
    session = sessionmaker(bind=engine)()

    @contextmanager
    def _this_store(_=None):
        yield session

    monkeypatch.setattr(tool_calls, "unit_of_work", _this_store)
    return session
