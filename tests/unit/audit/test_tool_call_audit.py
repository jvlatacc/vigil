"""The audit writer chains rows; the verifier proves the chain still holds.

These run over SQLite: what they test is the writer's contract -- one row per
call, linked by hash, carrying who and what -- which is dialect-independent.
The trigger-vs-writer agreement and the append-only grants are proven against
real Postgres in tests/integration/test_tool_call_audit.py.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from types import SimpleNamespace
from unittest.mock import MagicMock

from opentelemetry import trace

from core.audit import tool_calls
from core.storage.models import ToolCallAudit
from core.storage.models.base import Base

pytestmark = pytest.mark.unit


@pytest.fixture
def store(monkeypatch):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_is_integer_on_sqlite(type_, compiler, **kw):  # pragma: no cover
        return "INTEGER"

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[ToolCallAudit.__table__])
    session = sessionmaker(bind=engine)()

    @contextmanager
    def _this_store(_=None):
        yield session

    monkeypatch.setattr(tool_calls, "unit_of_work", _this_store)
    return session


def _record(store, **overrides):
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
    return tool_calls.record_tool_call(**fields)


def _rows(store):
    store.expire_all()
    return list(
        store.execute(select(ToolCallAudit).order_by(ToolCallAudit.id)).scalars()
    )


class TestArgsDigest:
    def test_the_digest_is_deterministic_and_order_free(self):
        one = tool_calls.hash_args({"a": 1, "b": [2, 3]})
        two = tool_calls.hash_args({"b": [2, 3], "a": 1})
        assert one == two
        assert one[0] is not None and len(one[0]) == 64
        assert one[1] is not None and one[1] > 0

    def test_no_arguments_digests_to_nothing(self):
        assert tool_calls.hash_args(None) == (None, None)


class TestTheTraceId:
    """The trace id is a correlation strength, never a condition."""

    @staticmethod
    def _span(trace_id):
        span = MagicMock()
        span.get_span_context.return_value = SimpleNamespace(trace_id=trace_id)
        return span

    def test_a_real_trace_is_spelled_in_hex(self, monkeypatch):
        monkeypatch.setattr(trace, "get_current_span", lambda: self._span(0xABC))
        assert tool_calls.current_trace_id() == format(0xABC, "032x")

    def test_no_trace_is_empty_not_zero(self, monkeypatch):
        monkeypatch.setattr(trace, "get_current_span", lambda: self._span(0))
        assert tool_calls.current_trace_id() is None

    def test_an_unreadable_context_is_telemetry_off(self, monkeypatch):
        # An instrumented stand-in whose trace id is not an int is the same
        # as telemetry being off: the row lands, the id stays empty.
        monkeypatch.setattr(
            trace, "get_current_span", lambda: self._span("not-an-int")
        )
        assert tool_calls.current_trace_id() is None


class TestTheWriter:
    def test_every_call_lands_one_row_carrying_who_and_what(self, store):
        _record(store, idp_subject="idp-123", run_id="run-9", trace_id="0af")

        (row,) = _rows(store)
        assert row.actor_username == "ada"
        assert row.idp_subject == "idp-123"
        assert row.surface == "agent"
        assert row.server_name == "github"
        assert row.tool_name == "github_search"
        assert row.decision == "allow"
        assert row.outcome == "ok"
        assert row.run_id == "run-9"
        assert row.trace_id == "0af"
        assert row.args_sha256 is not None and row.args_bytes is not None

    def test_rows_link_by_hash(self, store):
        _record(store)
        _record(store, tool_name="github_close")
        _record(store, tool_name="github_reopen", decision=tool_calls.DECISION_DENY)

        first, second, third = _rows(store)
        assert first.prev_hash == ""
        assert second.prev_hash == first.event_hash
        assert third.prev_hash == second.event_hash

    def test_a_deny_is_a_first_class_row(self, store):
        _record(
            store,
            decision=tool_calls.DECISION_DENY,
            deny_reason="permission",
            outcome=None,
        )

        (row,) = _rows(store)
        assert row.decision == "deny"
        assert row.deny_reason == "permission"
        assert tool_calls.verify_chain().ok


class TestTheVerifier:
    def test_a_stored_sequence_verifies(self, store):
        for i in range(4):
            _record(store, tool_name=f"tool_{i}", args={"i": i})

        verdict = tool_calls.verify_chain()
        assert verdict.ok is True
        assert verdict.checked == 4
        assert verdict.broken_at is None

    def test_an_empty_chain_verifies(self, store):
        verdict = tool_calls.verify_chain()
        assert verdict.ok is True
        assert verdict.checked == 0

    def test_a_tampered_row_breaks_the_chain_where_it_was_touched(self, store):
        for i in range(3):
            _record(store, tool_name=f"tool_{i}")
        target = _rows(store)[1]

        store.query(ToolCallAudit).filter(
            ToolCallAudit.id == target.id
        ).update({"outcome": "ok-but-edited"})
        store.commit()

        verdict = tool_calls.verify_chain()
        assert verdict.ok is False
        assert verdict.broken_at == target.id
