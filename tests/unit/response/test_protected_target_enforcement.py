"""A protected target waits for a person at the gate and in the executor.

Whatever the confidence says, containment naming a never-quarantine target
stays pending with the rule it was decided by; a rules read that fails holds
containment rather than deciding. Observing actions never pay the read.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from core.response.approval_service import (
    ActionStatus,
    ActionType,
    ApprovalService,
    PendingAction,
)
from core.response.autonomous_response_service import AutonomousResponseService
from core.response.config import ResponseConfig
from core.response.protected_targets import (
    ORIGIN_ENV,
    ORIGIN_OPERATOR,
    ProtectedTargetRules,
    current_rules,
    parse_entry,
)

pytestmark = pytest.mark.unit

GATE = "core.response.approval_service"


@pytest.fixture
def no_db():
    """Stand-in session and config store so ApprovalService never reaches
    PostgreSQL: not for the row _put_action inserts, and not for the
    force_manual_approval flag read at each decision."""
    manager = MagicMock()

    @contextmanager
    def _scope():
        yield MagicMock()

    manager.session_scope = _scope
    config_store = MagicMock()
    config_store.read_system_config.return_value = {"enabled": False}
    with (
        patch(f"{GATE}.get_db_manager", return_value=manager),
        patch(f"{GATE}.get_config_service", return_value=config_store),
    ):
        yield


def _env_rule():
    return parse_entry(
        "ip:10.0.0.5", ORIGIN_ENV, reason="the floor", created_by="environment"
    )


def _create(
    svc: ApprovalService,
    target: str,
    confidence: float,
    action_type=ActionType.BLOCK_IP,
):
    return svc.create_action(
        action_type=action_type,
        title="block",
        description="test",
        target=target,
        confidence=confidence,
        reason="test",
        evidence=[],
        created_by="pytest",
    )


def _pending(action_id, *, requires_approval, approved_by, target="203.0.113.7"):
    return PendingAction(
        action_id=action_id,
        action_type="waf_block",
        title="t",
        description="d",
        target=target,
        confidence=0.99,
        reason="r",
        evidence=[],
        created_at="",
        created_by="responder",
        requires_approval=requires_approval,
        status="approved",
        approved_by=approved_by,
    )


class _RulesService:
    """Executor stand-in: rows in, never-quarantine rules configured."""

    def __init__(self, rows, rules):
        self._rows = rows
        self._rules = rules
        self.executed = []
        self.failed = []

    def list_actions(self, status=None, **_):
        return self._rows

    def protected_target_rules(self):
        return self._rules

    def breaker_hold(self):
        # The executor honors the breaker each tick; the fake declares it
        # armed, so its rows decide on their own merits.
        return None

    def mark_executed(self, action_id, result):
        self.executed.append(action_id)

    def mark_failed(self, action_id, error):
        self.failed.append(action_id)


def _executor(rows, rules):
    service = AutonomousResponseService.__new__(AutonomousResponseService)
    service.approval_service = _RulesService(rows, rules)
    # The executor reads the quota knobs from the config its constructor
    # would set; __new__ skips that, so the helper supplies it directly.
    service.config = ResponseConfig()
    service._execute_cloudflare_action = lambda **_: {"success": True}
    return service


@pytest.mark.usefixtures("no_db")
class TestGateHoldsProtectedTargets:
    def test_a_protected_target_at_confidence_ninety_nine_stays_pending(self):
        svc = ApprovalService(config=ResponseConfig())
        with patch(f"{GATE}._active_protected_targets", return_value=(_env_rule(),)):
            action = _create(svc, "10.0.0.5", 0.99)
        assert action.status == ActionStatus.PENDING.value
        assert action.requires_approval is True
        assert "approval.protected_target=env:ip:10.0.0.5" in action.reason

    def test_an_operator_row_holds_too(self):
        rule = parse_entry(
            "cidr:10.0.0.0/8", ORIGIN_OPERATOR, reason="the core range", created_by="op"
        )
        svc = ApprovalService(config=ResponseConfig())
        with patch(f"{GATE}._active_protected_targets", return_value=(rule,)):
            action = _create(svc, "10.0.1.5", 0.99)
        assert action.status == ActionStatus.PENDING.value
        assert "approval.protected_target=operator:cidr:10.0.0.0/8" in action.reason

    def test_an_unprotected_target_still_auto_approves(self):
        svc = ApprovalService(config=ResponseConfig())
        with patch(f"{GATE}._active_protected_targets", return_value=(_env_rule(),)):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.APPROVED.value

    def test_a_failed_rules_read_holds_containment(self):
        svc = ApprovalService(config=ResponseConfig())
        with patch(
            f"{GATE}._active_protected_targets", side_effect=RuntimeError("db down")
        ):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.PENDING.value
        assert "approval.protected_target_read=failed" in action.reason

    def test_an_unparsed_env_entry_holds_containment(self):
        svc = ApprovalService(config=ResponseConfig(never_quarantine=("nope:zzz",)))
        action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.PENDING.value
        assert "approval.protected_target_unparsed" in action.reason

    def test_an_observing_action_never_pays_the_read(self):
        # An approval that went through proves the rules were never consulted:
        # a failed read would have held every containment action.
        svc = ApprovalService(config=ResponseConfig())
        with patch(
            f"{GATE}._active_protected_targets", side_effect=RuntimeError("db down")
        ):
            action = _create(
                svc, "203.0.113.7", 0.99, action_type=ActionType.EXECUTE_SPL_QUERY
            )
        assert action.status == ActionStatus.APPROVED.value


class TestExecutorLastLine:
    """A row that reached approved underneath the gate still cannot contain
    a protected target."""

    def test_a_protected_target_is_never_executed(self):
        rules = ProtectedTargetRules(floor=(_env_rule(),))
        svc = _executor(
            [
                _pending(
                    "h", requires_approval=True, approved_by="alice", target="10.0.0.5"
                )
            ],
            rules,
        )
        results = svc.execute_approved_actions()
        assert len(results) == 1
        assert results[0]["result"]["success"] is False
        assert "Never-quarantine invariant" in results[0]["result"]["error"]
        assert svc.approval_service.failed == ["h"]
        assert svc.approval_service.executed == []

    def test_an_unprotected_target_executes(self):
        rules = ProtectedTargetRules(floor=(_env_rule(),))
        svc = _executor(
            [_pending("h", requires_approval=True, approved_by="alice")],
            rules,
        )
        results = svc.execute_approved_actions()
        assert [r["action_id"] for r in results] == ["h"]
        assert svc.approval_service.executed == ["h"]

    def test_a_failed_rules_read_skips_the_tick(self):
        # A transient read error is not a decision: the row waits, unmarked.
        svc = _executor(
            [_pending("h", requires_approval=True, approved_by="alice")],
            current_rules(ResponseConfig(), read_failed=True),
        )
        assert svc.execute_approved_actions() == []
        assert svc.approval_service.executed == []
        assert svc.approval_service.failed == []

    def test_an_unparsed_floor_entry_skips_the_tick(self):
        svc = _executor(
            [_pending("h", requires_approval=True, approved_by="alice")],
            current_rules(ResponseConfig(never_quarantine=("nope:zzz",))),
        )
        assert svc.execute_approved_actions() == []
        assert svc.approval_service.executed == []
