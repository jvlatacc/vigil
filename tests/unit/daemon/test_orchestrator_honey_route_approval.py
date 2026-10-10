"""Run proposals of honey_route mint proper human_only rows (feature 5).

The orchestrator converts a run's ``proposed_actions`` into approval rows at
terminal review. A honey_route proposal must arrive as the honey_route type —
not the unknown-type fallback to CUSTOM — as a human_only row (the run's
confidence never releases it), and deduped per attacker with the rows the
daemon and the propose tool mint: ``honey_route:<ip>``. Other action types
keep this path's historical keying: CUSTOM fallback, one row per review.
"""

from asyncio import run as asyncio_run
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from core.response.approval_service import ActionType, ApprovalService
from services.daemon.orchestrator import Orchestrator

pytestmark = pytest.mark.unit

ATTACKER_IP = "203.0.113.7"


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


def _orchestrator() -> Orchestrator:
    orch = object.__new__(Orchestrator)
    orch._approvals = ApprovalService()
    return orch


def test_honey_route_proposal_mints_a_human_only_honey_route_row(stored_rows):
    asyncio_run(
        _orchestrator()._create_approval_action(
            "inv-1",
            {
                "action": "honey_route",
                "target": ATTACKER_IP,
                "reason": "repeated recon probes",
                "requires_approval": True,
            },
        )
    )

    (row,) = stored_rows
    assert row.action_type == ActionType.HONEY_ROUTE.value
    assert row.idempotency_key == f"honey_route:{ATTACKER_IP}"
    assert row.requires_approval is True
    assert row.status == "pending"
    assert row.created_by == "orchestrator"


def test_honey_route_proposal_reuses_the_daemon_or_tool_row(stored_rows):
    orch = _orchestrator()
    action = {
        "action": "honey_route",
        "target": ATTACKER_IP,
        "reason": "probes",
        "requires_approval": True,
    }
    asyncio_run(orch._create_approval_action("inv-1", action))
    asyncio_run(orch._create_approval_action("inv-2", action))

    assert len(stored_rows) == 1


def test_unknown_action_string_still_falls_back_to_custom(stored_rows):
    asyncio_run(
        _orchestrator()._create_approval_action(
            "inv-1",
            {"action": "teleport", "target": "host-1", "reason": "?"},
        )
    )

    (row,) = stored_rows
    assert row.action_type == ActionType.CUSTOM.value
    assert row.idempotency_key is None


def test_non_honey_route_proposals_keep_their_historical_path(stored_rows):
    # "isolate" is not an ActionType value (the member is isolate_host), so
    # run proposals of it have always landed on the CUSTOM fallback with no
    # idempotency key. PR5 changes that for honey_route only — every other
    # action string keeps this path's historical behaviour.
    asyncio_run(
        _orchestrator()._create_approval_action(
            "inv-1",
            {"action": "isolate", "target": "10.0.4.25", "reason": "critical"},
        )
    )

    (row,) = stored_rows
    assert row.action_type == ActionType.CUSTOM.value
    assert row.idempotency_key is None
