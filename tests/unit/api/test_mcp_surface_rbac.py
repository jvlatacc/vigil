"""The /mcp gate checks the caller's standing on tool calls, and records both.

The surface exposes Vigil's own tools only, so the scope a caller needs is the
baseline ``tools.execute`` grant: held, every tool here answers; not held, a
tool call is refused with a deny row -- first-class, like every other decision
the surface makes. Requests that run nothing (setup, discovery, pings) are
neither checked nor recorded.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from sqlalchemy import select

from core.audit import tool_calls
from core.integrations.mcp.surface import VIGIL_SERVER
from core.storage.models import ToolCallAudit

pytestmark = pytest.mark.unit


class _StubServer:
    """The MCP server app behind the gate, reduced to what the test observes."""

    def __init__(self, status: int = 200):
        self.status = status
        self.called = 0

    async def __call__(self, scope, receive, send):
        self.called += 1
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})


@pytest.fixture
def store(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from core.storage.models import ToolCallAudit
    from core.storage.models.base import Base

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


def _rows(store):
    store.expire_all()
    return list(
        store.execute(select(ToolCallAudit).order_by(ToolCallAudit.id)).scalars()
    )


def _gate(
    monkeypatch,
    server: _StubServer,
    *,
    allowed: bool,
    username: str = "vera",
):
    """The gate with its auth, permission and storage answers pinned."""
    from services.api import mcp_surface

    user = SimpleNamespace(user_id="u-1", username=username)
    monkeypatch.setattr(mcp_surface, "is_enabled", lambda: True)
    monkeypatch.setattr(mcp_surface, "authenticate", lambda token: user)
    monkeypatch.setattr(
        mcp_surface, "username_has_tool_permission", lambda u, s: allowed
    )
    return mcp_surface.McpSurfaceGate(server)


async def _post(gate, body: bytes = b"{}") -> int:
    scope: Dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [(b"authorization", b"Bearer some-credential")],
        "query_string": b"",
    }
    sent: List[Any] = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message) -> None:
        sent.append(message)

    await gate(scope, receive, send)
    return sent[0]["status"]


def _tool_call(name: str = "close_case", **arguments) -> bytes:
    import json

    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    ).encode()


class TestDeniedToolCalls:
    async def test_a_caller_without_the_grant_is_refused_and_recorded(
        self, monkeypatch, store
    ):
        server = _StubServer()
        gate = _gate(monkeypatch, server, allowed=False)

        status = await _post(gate, _tool_call(case_id="case-1"))

        assert status == 403
        assert server.called == 0  # the tool never ran
        rows = _rows(store)
        assert len(rows) == 1
        row = rows[0]
        assert row.actor_username == "vera"
        assert row.surface == tool_calls.SURFACE_MCP_INBOUND
        assert row.server_name == VIGIL_SERVER
        assert row.tool_name == "close_case"
        assert row.decision == tool_calls.DECISION_DENY
        assert row.deny_reason == "permission"
        assert row.args_sha256 is not None
        assert row.args_bytes is not None

    async def test_a_write_that_fails_fails_the_request(
        self, monkeypatch, store
    ):
        """The deny row is the enforcement record; without it there is none."""
        from services.api import mcp_surface

        server = _StubServer()
        gate = _gate(monkeypatch, server, allowed=False)

        @contextmanager
        def _broken_store(_=None):
            raise RuntimeError("audit store down")
            yield  # pragma: no cover

        monkeypatch.setattr(tool_calls, "unit_of_work", _broken_store)
        with pytest.raises(RuntimeError):
            await _post(gate, _tool_call())
        assert server.called == 0


class TestAllowedToolCalls:
    async def test_a_granted_call_runs_and_lands_one_row(self, monkeypatch, store):
        server = _StubServer()
        gate = _gate(monkeypatch, server, allowed=True, username="rory")

        status = await _post(gate, _tool_call(case_id="case-1"))

        assert status == 200
        assert server.called == 1
        rows = _rows(store)
        assert len(rows) == 1
        row = rows[0]
        assert row.actor_username == "rory"
        assert row.decision == tool_calls.DECISION_ALLOW
        assert row.outcome == "ok"
        assert row.duration_ms is not None

    async def test_the_server_answer_decides_the_outcome(self, monkeypatch, store):
        server = _StubServer(status=500)
        gate = _gate(monkeypatch, server, allowed=True)

        status = await _post(gate, _tool_call())

        assert status == 500
        row = _rows(store)[0]
        assert row.decision == tool_calls.DECISION_ALLOW
        assert row.outcome == "error"


class TestWhatIsNotAToolCall:
    async def test_protocol_traffic_is_neither_checked_nor_recorded(
        self, monkeypatch, store
    ):
        server = _StubServer()
        gate = _gate(monkeypatch, server, allowed=False)

        status = await _post(gate, b'{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}')

        assert status == 200
        assert server.called == 1  # setup reaches the server unimpeded
        assert _rows(store) == []

    async def test_a_body_that_does_not_parse_is_the_servers_to_answer(
        self, monkeypatch, store
    ):
        server = _StubServer()
        gate = _gate(monkeypatch, server, allowed=False)

        status = await _post(gate, b"not json")

        assert status == 200
        assert _rows(store) == []

    async def test_a_get_stream_is_not_a_tool_call(self, monkeypatch, store):
        from services.api import mcp_surface

        server = _StubServer()
        gate = _gate(monkeypatch, server, allowed=False)

        scope: Dict[str, Any] = {
            "type": "http",
            "method": "GET",
            "path": "/mcp",
            "headers": [(b"authorization", b"Bearer some-credential")],
            "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        sent: List[Any] = []

        async def send(message) -> None:
            sent.append(message)

        await gate(scope, receive, send)
        assert server.called == 1
        assert _rows(store) == []
