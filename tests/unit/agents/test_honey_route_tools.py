"""The deception tools: propose mints a human_only row, execute is a person's call.

Feature 5's agent path. Proposing needs no permission and steers nothing — the
row waits for a person whatever confidence the run names, keyed per attacker
(``honey_route:<ip>``) so a proposal and the daemon's own minting converge on
one row. The execute form is approve_action's chain: no bound caller, no
permission, no execution; and a PENDING row is never executed, because that
would bypass the human decision the row is held for.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from core.agents import tool_registry
from core.config import get_settings
from core.integrations.mcp.surface import acting_as
from core.llm.tool_schemas import ALL_TOOLS
from core.response.approval_service import PendingAction
from tools.mcp.vigil import FROZEN_TOOLS

pytestmark = pytest.mark.unit

ATTACKER_IP = "203.0.113.7"


@pytest.fixture
def posture_on(monkeypatch):
    monkeypatch.setenv("DAEMON_DECEPTION_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def stored_rows():
    """The no-PostgreSQL stand-in behind ApprovalService._put_action.

    Same shape as tests/unit/response/test_mcp_approval_actions.py: the
    session remembers ``add`` so a later key lookup sees the insert.
    """
    stored = []
    session = MagicMock()

    def add(row):
        stored.append(row)

    def execute(stmt):
        rows = [row for row in stored if _matches(row, stmt)]
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        result.scalar_one_or_none.return_value = rows[0] if rows else None
        return result

    session.add.side_effect = add
    session.execute.side_effect = execute

    manager = MagicMock()

    @contextmanager
    def _scope():
        yield session

    manager.session_scope = _scope

    config_store = MagicMock()
    config_store.read_system_config.return_value = {"enabled": False}
    with (
        patch("core.response.approval_service.get_db_manager", return_value=manager),
        patch(
            "core.response.approval_service.get_config_service",
            return_value=config_store,
        ),
    ):
        yield stored


def _matches(row, stmt) -> bool:
    for clause in stmt._where_criteria:
        # Evaluate the clause's own operator — the status filter is ``ne``
        # ("not failed"), and an equality-only helper would invert it.
        if not clause.operator(getattr(row, clause.left.key), clause.right.value):
            return False
    return True


def _pending(action_id="action-1", action_type="honey_route", status="approved"):
    return PendingAction(
        action_id=action_id,
        action_type=action_type,
        title="Honey Route: " + ATTACKER_IP,
        description="d",
        target=ATTACKER_IP,
        confidence=0.9,
        reason="r",
        evidence=[],
        created_at="2026-10-09T00:00:00Z",
        created_by="investigator",
        requires_approval=True,
        status=status,
        parameters={"attacker_ip": ATTACKER_IP},
    )


@pytest.mark.usefixtures("posture_on", "stored_rows")
def test_propose_mints_a_pending_row_a_person_must_decide(monkeypatch):
    monkeypatch.setenv("DAEMON_CONFIDENCE_THRESHOLD", "0.90")
    get_settings.cache_clear()
    try:
        result = tool_registry.propose_honey_route(
            attacker_ip=ATTACKER_IP,
            reason="repeated T1595 probes",
            destination_ips=["10.0.4.25"],
            ports=[445, 3389],
            # A run's own claim — it must never release the row.
            confidence=0.99,
            evidence=["f-1", "f-2"],
        )
    finally:
        get_settings.cache_clear()

    assert result["success"] is True
    assert result["status"] == "pending"
    assert result["requires_approval"] is True


@pytest.mark.usefixtures("posture_on")
def test_propose_keys_the_row_per_attacker_like_the_daemon(stored_rows):
    tool_registry.propose_honey_route(
        attacker_ip=ATTACKER_IP, reason="probes", ports=[445]
    )

    (row,) = stored_rows
    assert row.action_type == "honey_route"
    assert row.idempotency_key == f"honey_route:{ATTACKER_IP}"
    assert row.requires_approval is True
    assert row.status == "pending"
    assert row.created_by == "investigator"
    assert row.parameters["ports"] == [445]
    assert row.parameters["destination_ips"] == []


@pytest.mark.usefixtures("posture_on")
def test_propose_twice_reuses_one_row_per_attacker(stored_rows):
    first = tool_registry.propose_honey_route(attacker_ip=ATTACKER_IP, reason="probes")
    second = tool_registry.propose_honey_route(
        attacker_ip=ATTACKER_IP, reason="probes again"
    )

    assert len(stored_rows) == 1
    assert second["action_id"] == first["action_id"]


@pytest.mark.usefixtures("stored_rows")
def test_propose_needs_no_permission_and_no_bound_caller(posture_on):
    # No acting_as binding, no permission stub: a hunt — nobody bound — may
    # propose, because the proposal is inert until a person decides.
    result = tool_registry.propose_honey_route(attacker_ip=ATTACKER_IP, reason="r")
    assert result["success"] is True


@pytest.mark.usefixtures("stored_rows")
def test_propose_refuses_when_the_posture_is_disabled():
    result = tool_registry.propose_honey_route(attacker_ip=ATTACKER_IP, reason="r")
    assert "disabled" in result["error"]


@pytest.mark.parametrize("ip", ["", "unknown", "   "])
@pytest.mark.usefixtures("posture_on")
def test_propose_needs_a_source_ip(ip, stored_rows):
    result = tool_registry.propose_honey_route(attacker_ip=ip, reason="r")
    assert "error" in result
    assert stored_rows == []


def test_deception_tools_are_backend_tools_not_frozen():
    for name in ("propose_honey_route", "execute_honey_route"):
        assert name in {tool["name"] for tool in ALL_TOOLS}
        assert name in tool_registry._OWNED
        # The vigil MCP server stays untouched: these are backend tools, and
        # freezing one would trip the frozen-tools snapshot ratchet.
        assert name not in FROZEN_TOOLS


def test_execute_refuses_an_unbound_caller():
    response = MagicMock()
    with patch.object(tool_registry, "_response", return_value=response):
        result = tool_registry.execute_honey_route(action_id="action-1")

    assert "no principal is bound" in result["error"]
    response.execute_honey_route_action.assert_not_called()


def test_execute_requires_the_approval_permission(monkeypatch):
    monkeypatch.setattr(tool_registry, "username_has_permission", lambda *a, **k: False)
    with acting_as("analyst"):
        result = tool_registry.execute_honey_route(action_id="action-1")
    assert "may not decide approvals" in result["error"]


@pytest.mark.parametrize(
    "action",
    [
        # A pending row: executing it would bypass the person deciding.
        _pending(status="pending"),
        # Not a honey-route row at all.
        _pending(action_type="isolate_host"),
    ],
)
def test_execute_refuses_rows_a_person_has_not_approved(monkeypatch, action):
    monkeypatch.setattr(tool_registry, "username_has_permission", lambda *a, **k: True)
    approvals = MagicMock()
    approvals.get_action.return_value = action
    response = MagicMock()
    with (
        patch.object(tool_registry, "_approvals", lambda: approvals),
        patch.object(tool_registry, "_response", return_value=response),
        acting_as("analyst"),
    ):
        result = tool_registry.execute_honey_route(action_id=action.action_id)

    assert "error" in result
    response.execute_honey_route_action.assert_not_called()


def test_execute_runs_the_sweep_arm_on_an_approved_row(monkeypatch):
    monkeypatch.setattr(tool_registry, "username_has_permission", lambda *a, **k: True)
    action = _pending(status="approved")
    approvals = MagicMock()
    approvals.get_action.return_value = action
    response = MagicMock()
    response.execute_honey_route_action.return_value = {
        "success": True,
        "lease_id": "lease-1",
        "rollback": "DELETE /steer/lease-1",
    }
    with (
        patch.object(tool_registry, "_approvals", lambda: approvals),
        patch.object(tool_registry, "_response", return_value=response),
        acting_as("analyst"),
    ):
        result = tool_registry.execute_honey_route(action_id=action.action_id)

    response.execute_honey_route_action.assert_called_once_with(action)
    assert result["success"] is True
    assert result["action_id"] == action.action_id
