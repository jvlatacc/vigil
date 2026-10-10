"""The dispatch gate: a mutating integration tool queues for a person.

E2 (spec area B): ``mde_isolate`` posted ``IsolationType: Full``,
``cb_quarantine`` pulled a device off the network, and ART executed attack
techniques -- all on the agent's say-so, because the approval pipeline lived
in prompts. These pin the technical gate in ``execute_mcp_tool``: a
descriptor-declared or fail-closed-pattern tool returns the queued action id
instead of dispatching, read-only tools dispatch unchanged, and the queued
row carries the caller's identity -- never ``agent``.

The stub registry exposes ``x_isolate`` the way the spec's acceptance test
describes. On the pre-fix code these fail by construction: there is no gate,
the stubbed client answers the call, and no approval row is ever created.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from core.agents.mcp_tools import execute_mcp_tool  # noqa: E402

pytestmark = pytest.mark.unit

SERVER = "stub-server"
ISOLATE = f"{SERVER}_x_isolate"
LIST_ALERTS = f"{SERVER}_x_list_alerts"
STATUS = f"{SERVER}_get_isolation_status"


class _StubRegistry:
    """Just enough of MCPRegistry for execute_mcp_tool's two lookups."""

    def __init__(self, servers, names):
        self._servers = list(servers)
        self._names = list(names)

    def get_active_servers(self):
        return list(self._servers)

    def get_tool_names(self):
        return list(self._names)


class _RecordingApprovals:
    """Stands in for ApprovalService; records what the gate asked to queue."""

    def __init__(self):
        self.calls = []

    def create_action(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(action_id="action-test-0001")


class _StubClient:
    """The MCP client execute_mcp_tool would dispatch through."""

    def __init__(self):
        self.calls = []

    async def call_tool(self, server, tool, args, timeout=30.0):
        self.calls.append((server, tool, args))
        return {"content": [{"type": "text", "text": '{"alerts": []}'}]}


@pytest.fixture
def approvals(monkeypatch):
    service = _RecordingApprovals()
    monkeypatch.setattr("core.agents.mcp_tools._approval_service", lambda: service)
    return service


@pytest.fixture
def client(monkeypatch):
    stub = _StubClient()
    monkeypatch.setattr("core.integrations.mcp.client.process_mcp_client", lambda: stub)
    return stub


async def _queue_and_check(tool_name, registry, approvals, client):
    from core.integrations.mcp import surface

    with surface.acting_as("analyst-nora@corp.example"):
        result, handled = await execute_mcp_tool(tool_name, {}, 5.0, registry)
    assert handled is True
    assert result == {"queued_for_approval": "action-test-0001", "tool": tool_name}
    assert client.calls == []  # nothing dispatched
    return approvals.calls[0]


async def test_a_mutating_tool_queues_for_approval(approvals, client):
    await _queue_and_check(
        ISOLATE, _StubRegistry([SERVER], [ISOLATE, LIST_ALERTS]), approvals, client
    )


async def test_a_descriptor_declaration_gates_where_the_pattern_cannot(
    approvals, client
):
    # pagerduty_manage_incidents ends in a noun, so the fail-closed pattern
    # is silent; the shipped descriptor declares it mutating, and the gate
    # queues it -- this is the E5 hole that name tokens alone cannot close.
    queued = await _queue_and_check(
        "pagerduty_manage_incidents",
        _StubRegistry([SERVER, "pagerduty"], ["pagerduty_manage_incidents"]),
        approvals,
        client,
    )
    assert queued["parameters"]["tool"] == "pagerduty_manage_incidents"


async def test_the_queued_row_carries_the_caller_and_the_ask(approvals, client):
    registry = _StubRegistry([SERVER], [ISOLATE, LIST_ALERTS])
    queued = await _queue_and_check(ISOLATE, registry, approvals, client)

    assert queued["created_by"] == "analyst-nora@corp.example"  # never "agent"
    assert queued["human_only"] is True
    assert queued["reason"] == "mutating integration tool requires human approval"
    assert queued["parameters"]["tool"] == ISOLATE


async def test_an_unbound_call_is_not_recorded_as_an_agent(approvals, client):
    # A hunt binds no principal: the row records the system rather than
    # dressing the call up as its requester.
    registry = _StubRegistry([SERVER], [ISOLATE, LIST_ALERTS])
    await execute_mcp_tool(ISOLATE, {}, 5.0, registry)
    assert approvals.calls[0]["created_by"] == "system"


async def test_a_read_only_tool_dispatches_unchanged(approvals, client):
    registry = _StubRegistry([SERVER], [ISOLATE, LIST_ALERTS])
    rows, handled = await execute_mcp_tool(LIST_ALERTS, {}, 5.0, registry)

    assert handled is True
    assert rows == [{"alerts": []}]
    assert client.calls == [(SERVER, "x_list_alerts", {})]
    assert approvals.calls == []


async def test_a_read_only_lead_verb_never_queues(approvals, client):
    # get_isolation_status ends in a mutating noun's neighbourhood but reads:
    # the pattern is suffix-anchored, so only a trailing verb fires it.
    registry = _StubRegistry([SERVER], [STATUS, ISOLATE])
    rows, handled = await execute_mcp_tool(STATUS, {}, 5.0, registry)

    assert handled is True
    assert client.calls == [(SERVER, "get_isolation_status", {})]
    assert approvals.calls == []


async def test_the_name_pattern_fails_closed_without_a_descriptor(approvals, client):
    # stub-server has no descriptor: classification is the name pattern
    # alone, and an unknown-but-mutating-shaped name queues rather than
    # executes. An unknown tool is refused earlier (handled False) -- this
    # one is registered, just shaped like the world-changers.
    await _queue_and_check(
        f"{SERVER}_x_purge",
        _StubRegistry([SERVER], [f"{SERVER}_x_purge"]),
        approvals,
        client,
    )
