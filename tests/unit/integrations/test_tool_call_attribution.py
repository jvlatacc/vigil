"""Every dispatch surface records who was behind the call.

The enforcement rows — the agent boundary and the /mcp gate — landed with
the audit writer. This file covers the execution surfaces: the outbound
vendor funnel, Vigil's own in-process tools, and the VStrike client. Each
writes the row for allow and error alike, and the actor is whoever
``current_caller()`` binds at the moment of the call — never a parameter the
dispatcher could have guessed at. VStrike's row is the interesting one: the
service-account JWT is what the far side sees, so the row is the only place
the person still exists.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx
from sqlalchemy import select

import core.integrations.vstrike.client as vstrike_client
from core.audit import tool_calls
from core.integrations.mcp import in_process
from core.integrations.mcp.client import MCPClient
from core.integrations.mcp.surface import acting_as
from core.integrations.vstrike.client import VStrikeService
from core.storage.models import ToolCallAudit

pytestmark = pytest.mark.unit

_BASE = "https://vstrike-audit.example.com"


def _rows(store):
    store.expire_all()
    return list(
        store.execute(select(ToolCallAudit).order_by(ToolCallAudit.id)).scalars()
    )


# --------------------------------------------------------------------- #
# The outbound vendor funnel (MCPClient.call_tool)
# --------------------------------------------------------------------- #


class _Service:
    """Just enough MCPService for the funnel: one known server."""

    servers = {"demo": object()}

    def is_server_enabled(self, name):
        return True


def _session(result=None, error=None):
    """A persistent session that answers, or raises, as the real one does."""

    async def call_tool(tool, args):
        if error is not None:
            raise error
        return result

    session = MagicMock()
    session.call_tool = call_tool
    return session


def _client_with_session(result=None, error=None):
    client = MCPClient(_Service())
    client.persistent_sessions["demo"] = _session(result, error)
    return client


_OK = {"error": False, "content": [{"type": "text", "text": "ok"}]}


async def test_funnel_row_carries_the_bound_caller(audit_store):
    client = _client_with_session(_OK)
    with acting_as("ada"):
        result = await client.call_tool("demo", "do_it", {"query": "x"})

    assert result["error"] is False
    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.surface == tool_calls.SURFACE_MCP_CLIENT
    assert row.server_name == "demo"
    assert row.tool_name == "do_it"
    assert row.decision == tool_calls.DECISION_ALLOW
    assert row.outcome == "ok"
    assert row.args_sha256 == tool_calls.hash_args({"query": "x"})[0]
    assert row.duration_ms is not None


async def test_funnel_row_for_a_server_reported_error(audit_store):
    server_error = {"error": True, "content": [{"type": "text", "text": "vendor said no"}]}
    client = _client_with_session(server_error)
    with acting_as("ada"):
        result = await client.call_tool("demo", "do_it", {})

    assert result["error"] is True
    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.outcome == "error"


async def test_funnel_row_for_a_timeout(audit_store):
    client = _client_with_session(error=asyncio.TimeoutError())
    with acting_as("ada"):
        result = await client.call_tool("demo", "do_it", {}, timeout=0.05)

    assert "timed out" in result["content"][0]["text"]
    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.outcome == "error"


async def test_funnel_row_for_a_refused_connect(audit_store):
    # No persistent session yet, and the connect attempt fails: the funnel's
    # connect-failure answer is still a dispatch somebody made.
    client = MCPClient(_Service())
    with acting_as("ada"):
        result = await client.call_tool("demo", "do_it", {})

    assert result["error"] is True
    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.server_name == "demo"
    assert row.outcome == "error"


async def test_funnel_row_for_an_unknown_server(audit_store):
    client = MCPClient(_Service())
    with acting_as("ada"):
        result = await client.call_tool("nosuch", "do_it", {})

    assert "Unknown server" in result["content"][0]["text"]
    (row,) = _rows(audit_store)
    assert row.server_name == "nosuch"
    assert row.actor_username == "ada"
    assert row.outcome == "error"


async def test_funnel_row_without_a_caller_is_the_agents(audit_store):
    client = _client_with_session(_OK)
    await client.call_tool("demo", "do_it", {})

    (row,) = _rows(audit_store)
    assert row.actor_username == tool_calls.ACTOR_AGENT


async def test_the_span_names_the_actor(audit_store):
    span = MagicMock()
    tracer = MagicMock()
    tracer.start_span.return_value = span
    client = _client_with_session(_OK)
    with acting_as("ada"), patch("core.telemetry.get_tracer", return_value=tracer):
        await client.call_tool("demo", "do_it", {})

    attributes = tracer.start_span.call_args.kwargs["attributes"]
    assert attributes["vigil.actor"] == "ada"
    # The row and the span are the two halves of the attribution contract;
    # they must spell the actor the same way.
    (row,) = _rows(audit_store)
    assert row.actor_username == attributes["vigil.actor"]


# --------------------------------------------------------------------- #
# Vigil's own tools, called in this process (in_process.call_tool)
# --------------------------------------------------------------------- #


class _VigilServer:
    """A stand-in for Vigil's own server, like the equivalence suite's."""

    def __init__(self, is_error: bool = False):
        self._is_error = is_error

    async def call_tool(self, name, args):
        return SimpleNamespace(
            is_error=self._is_error,
            content=[SimpleNamespace(text='{"ok": true}')],
        )


async def test_in_process_row_carries_the_bound_caller(audit_store, monkeypatch):
    monkeypatch.setattr(in_process, "_server", lambda: _VigilServer())
    with acting_as("ada"):
        result = await in_process.call_tool("case_search", {"query": "x"})

    assert result["error"] is False
    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.surface == tool_calls.SURFACE_IN_PROCESS
    assert row.server_name == "vigil"
    assert row.tool_name == "case_search"
    assert row.outcome == "ok"


async def test_in_process_row_for_a_tool_that_errors(audit_store, monkeypatch):
    monkeypatch.setattr(in_process, "_server", lambda: _VigilServer(is_error=True))
    with acting_as("ada"):
        result = await in_process.call_tool("case_search", {})

    assert result["error"] is True
    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.outcome == "error"


async def test_in_process_row_for_a_timeout(audit_store, monkeypatch):
    class _Slow:
        async def call_tool(self, name, args):
            await asyncio.sleep(5)

    monkeypatch.setattr(in_process, "_server", lambda: _Slow())
    with acting_as("ada"):
        result = await in_process.call_tool("case_search", {}, timeout=0.05)

    assert result["error"] is True
    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.outcome == "error"


# --------------------------------------------------------------------- #
# The VStrike client (service account upstream, person in the row)
# --------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _fresh_jwt_cache():
    """The module-level JWT cache must not leak between these tests."""
    vstrike_client._jwt_cache.clear()
    vstrike_client._jwt_login_locks.clear()
    yield
    vstrike_client._jwt_cache.clear()
    vstrike_client._jwt_login_locks.clear()


def _vstrike() -> VStrikeService:
    return VStrikeService(
        base_url=_BASE,
        verify_ssl=False,
        username="deeptempo_manager",
        password="secret",
    )


def _stub_login() -> None:
    respx.post(f"{_BASE}/mcp-login").mock(
        return_value=httpx.Response(200, json={"jsonwebtoken": "svc-jwt"})
    )


@respx.mock
def test_vstrike_rest_row_carries_the_caller_while_the_service_jwt_rides_upstream(
    audit_store,
):
    _stub_login()
    upstream = respx.get(f"{_BASE}/api/v1/topology/asset/a1").mock(
        return_value=httpx.Response(200, json={"neighbors": []})
    )

    service = _vstrike()
    with acting_as("ada"):
        topology = service.get_asset_topology("a1")

    assert topology == {"neighbors": []}
    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.surface == tool_calls.SURFACE_VSTRIKE
    assert row.server_name == "vstrike"
    assert row.tool_name == "GET /api/v1/topology/asset/a1"
    assert row.decision == tool_calls.DECISION_ALLOW
    assert row.outcome == "ok"
    # The service account is what VStrike saw; the person is what the row says.
    assert upstream.calls.last.request.headers["Authorization"] == "Bearer svc-jwt"


@respx.mock
def test_vstrike_rest_row_for_a_network_error(audit_store):
    _stub_login()
    respx.get(f"{_BASE}/api/v1/topology/asset/a1").mock(
        side_effect=httpx.ConnectError("down")
    )

    service = _vstrike()
    with acting_as("ada"):
        result = service.get_asset_topology("a1")

    # The helper catches the transport error, as it always did; the row was
    # already written by then.
    assert result is None
    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.outcome == "error"


@respx.mock
def test_vstrike_rest_retry_is_one_call_one_row(audit_store):
    _stub_login()
    upstream = respx.get(f"{_BASE}/api/v1/topology/asset/a1").mock(
        side_effect=[
            httpx.Response(401, text="stale token"),
            httpx.Response(200, json={"neighbors": []}),
        ]
    )

    service = _vstrike()
    with acting_as("ada"):
        service.get_asset_topology("a1")

    assert upstream.call_count == 2  # the 401 retry ran as before
    assert len(_rows(audit_store)) == 1  # and the call is one row, not two


@respx.mock
def test_vstrike_mcp_row_carries_the_caller_and_the_service_jwt(audit_store):
    _stub_login()
    upstream = respx.post(f"{_BASE}/mcp").mock(
        return_value=httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": {"content": []}},
        )
    )

    service = _vstrike()
    with acting_as("ada"):
        result = service._call_mcp_tool("network-list", {"network": "corp"})

    assert result == {"content": []}
    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.tool_name == "network-list"
    assert row.outcome == "ok"
    assert upstream.calls.last.request.headers["Authorization"] == "Bearer svc-jwt"


@respx.mock
def test_vstrike_mcp_row_for_an_upstream_error(audit_store):
    _stub_login()
    respx.post(f"{_BASE}/mcp").mock(return_value=httpx.Response(500, text="boom"))

    service = _vstrike()
    with acting_as("ada"), pytest.raises(RuntimeError):
        service._call_mcp_tool("network-list", {})

    (row,) = _rows(audit_store)
    assert row.actor_username == "ada"
    assert row.tool_name == "network-list"
    assert row.outcome == "error"


@respx.mock
def test_vstrike_row_without_a_caller_is_the_agents(audit_store):
    _stub_login()
    respx.get(f"{_BASE}/api/v1/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    service = _vstrike()
    ok, message = service.test_connection()

    assert ok is True
    (row,) = _rows(audit_store)
    assert row.actor_username == tool_calls.ACTOR_AGENT
