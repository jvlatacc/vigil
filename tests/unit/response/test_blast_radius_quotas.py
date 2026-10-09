"""Blast radius is a budget: unattended containment stops when the cap says so.

The (cap+1)th containment in an executor tick, and in a target subnet over
the rolling hour, waits for a person with the rule it was decided by — and a
failed counts read holds containment rather than deciding. Observing actions
and rows already held for another reason never pay the counts read.
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
from core.response.config import (
    ContainmentCounts,
    ResponseConfig,
    blast_bound_decision,
    containment_subnet,
)
from core.response.protected_targets import ORIGIN_ENV, parse_entry

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


# --- pure decision -----------------------------------------------------------


def test_an_under_cap_tick_and_hour_allow_the_row():
    assert (
        blast_bound_decision(
            ContainmentCounts(tick=2, subnet_hour=9, subnet_size=256), ResponseConfig()
        )
        is None
    )


def test_the_tick_cap_holds_with_its_rule():
    rule = blast_bound_decision(
        ContainmentCounts(tick=3, subnet_hour=0, subnet_size=256), ResponseConfig()
    )
    assert rule == "response.max_containment_per_tick=3 met (3)"


def test_the_subnet_hour_cap_holds_with_its_rule():
    rule = blast_bound_decision(
        ContainmentCounts(tick=0, subnet_hour=10, subnet_size=256), ResponseConfig()
    )
    assert rule == "response.max_containment_per_subnet_hour=10 met (10)"


def test_the_share_governs_when_it_is_the_smaller_bound():
    # 10% of 16 addresses is 1 (int-truncated): the second containment in
    # that hour holds even though the absolute floor would allow ten.
    assert (
        blast_bound_decision(
            ContainmentCounts(tick=0, subnet_hour=1, subnet_size=16), ResponseConfig()
        )
        == "response.max_containment_per_subnet_hour=1 met (1)"
    )


def test_the_share_multiplies_in_decimal_not_float():
    # 0.29 * 100 is 29; a float multiply lands at 28.999... and would
    # truncate to 28, silently tightening an operator's dial.
    config = ResponseConfig(
        max_containment_share_per_hour=0.29, max_containment_per_subnet_hour=50
    )
    assert (
        blast_bound_decision(
            ContainmentCounts(tick=0, subnet_hour=28, subnet_size=100), config
        )
        is None
    )
    assert (
        blast_bound_decision(
            ContainmentCounts(tick=0, subnet_hour=29, subnet_size=100), config
        )
        == "response.max_containment_per_subnet_hour=29 met (29)"
    )


def test_the_absolute_floor_caps_a_loose_share():
    # The share bound only tightens: 29% of 100 addresses is 29, but the
    # operator's absolute ceiling of 10 still governs.
    config = ResponseConfig(max_containment_share_per_hour=0.29)
    assert (
        blast_bound_decision(
            ContainmentCounts(tick=0, subnet_hour=10, subnet_size=100), config
        )
        == "response.max_containment_per_subnet_hour=10 met (10)"
    )


def test_the_absolute_floor_never_undercuts_the_share():
    # A /26 is 64 addresses; 10% is 6 — the floor of 10 cannot loosen the
    # share bound. A /24 is 256; 10% is 25 — the floor of 10 binds.
    tight = blast_bound_decision(
        ContainmentCounts(tick=0, subnet_hour=6, subnet_size=64), ResponseConfig()
    )
    loose = blast_bound_decision(
        ContainmentCounts(tick=0, subnet_hour=10, subnet_size=256), ResponseConfig()
    )
    assert tight == "response.max_containment_per_subnet_hour=6 met (6)"
    assert loose == "response.max_containment_per_subnet_hour=10 met (10)"


def test_a_share_that_rounds_to_zero_still_allows_one_containment():
    # 0.10 of 8 addresses truncates to 0; the max(..., 1) floor keeps a
    # tiny subnet from being uncontainable while staying bounded.
    assert (
        blast_bound_decision(
            ContainmentCounts(tick=0, subnet_hour=1, subnet_size=8), ResponseConfig()
        )
        == "response.max_containment_per_subnet_hour=1 met (1)"
    )


def test_an_unknown_subnet_size_is_bounded_by_the_absolute_cap_alone():
    assert (
        blast_bound_decision(
            ContainmentCounts(tick=0, subnet_hour=10, subnet_size=0), ResponseConfig()
        )
        == "response.max_containment_per_subnet_hour=10 met (10)"
    )
    assert (
        blast_bound_decision(
            ContainmentCounts(tick=0, subnet_hour=9, subnet_size=0), ResponseConfig()
        )
        is None
    )


def test_the_tick_cap_is_computed_on_the_configured_value():
    config = ResponseConfig(max_containment_per_tick=5)
    assert (
        blast_bound_decision(
            ContainmentCounts(tick=5, subnet_hour=0, subnet_size=0), config
        )
        == "response.max_containment_per_tick=5 met (5)"
    )


# --- the subnet a target's blast radius is measured in -----------------------


def test_a_subnet_spans_its_prefix_and_grouping_is_by_network_address():
    config = ResponseConfig()
    assert containment_subnet("10.0.0.5", config) == containment_subnet(
        "10.0.0.200", config
    )
    assert containment_subnet("10.0.0.5", config) != containment_subnet(
        "10.0.1.5", config
    )


def test_an_ipv6_target_uses_the_slash_sixty_four_analog():
    config = ResponseConfig()
    subnet = containment_subnet("2001:db8:1::5", config)
    assert subnet.num_addresses == 2**64
    assert subnet == containment_subnet("2001:db8:1::dead", config)


def test_an_ipv4_mapped_ipv6_target_normalises_to_its_ipv4_subnet():
    config = ResponseConfig()
    assert containment_subnet("::ffff:10.0.0.5", config) == containment_subnet(
        "10.0.0.9", config
    )


def test_a_configured_prefix_narrows_or_widens_the_subnet():
    narrow = ResponseConfig(containment_subnet_prefix=28)
    assert containment_subnet("10.0.0.5", narrow).num_addresses == 16


def test_a_hostname_counts_in_no_subnet():
    assert containment_subnet("gateway.corp.example", ResponseConfig()) is None


# --- the gate ----------------------------------------------------------------


def _create(
    svc: ApprovalService,
    target: str,
    confidence: float,
    action_type=ActionType.BLOCK_IP,
    **kwargs,
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
        **kwargs,
    )


@pytest.mark.usefixtures("no_db")
class TestGateHoldsContainmentOverQuota:
    def test_the_cap_plus_oneth_containment_in_a_tick_waits_for_a_person(self):
        svc = ApprovalService(config=ResponseConfig())
        counts = ContainmentCounts(tick=3, subnet_hour=0, subnet_size=256)
        with patch(f"{GATE}._containment_counts", return_value=counts):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.PENDING.value
        assert action.requires_approval is True
        assert "response.max_containment_per_tick=3 met (3)" in action.reason

    def test_a_row_under_the_caps_still_auto_approves(self):
        svc = ApprovalService(config=ResponseConfig())
        counts = ContainmentCounts(tick=0, subnet_hour=0, subnet_size=256)
        with patch(f"{GATE}._containment_counts", return_value=counts):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.APPROVED.value
        assert action.requires_approval is False

    def test_the_cap_plus_oneth_in_a_subnet_hour_waits_for_a_person(self):
        svc = ApprovalService(config=ResponseConfig())
        counts = ContainmentCounts(tick=0, subnet_hour=10, subnet_size=256)
        with patch(f"{GATE}._containment_counts", return_value=counts):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.PENDING.value
        assert "response.max_containment_per_subnet_hour=10 met (10)" in action.reason

    def test_a_failed_counts_read_holds_containment_for_a_person(self):
        svc = ApprovalService(config=ResponseConfig())
        with patch(f"{GATE}._containment_counts", side_effect=RuntimeError("db down")):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.PENDING.value
        assert "response.containment_counts_read=failed" in action.reason

    def test_a_quoted_row_keeps_its_place_in_the_queue(self):
        # Held, not dropped: the row keeps the caller's reason plus the rule.
        svc = ApprovalService(config=ResponseConfig())
        counts = ContainmentCounts(tick=3, subnet_hour=0, subnet_size=256)
        with patch(f"{GATE}._containment_counts", return_value=counts):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.reason.startswith("test;")
        assert "response.max_containment_per_tick=3 met (3)" in action.reason

    def test_a_row_already_held_for_another_reason_never_pays_the_counts_read(self):
        # A human_only row's outcome is decided; reading counts could only
        # change the rule string, never the person-requirement.
        svc = ApprovalService(config=ResponseConfig())
        counts = ContainmentCounts(tick=99, subnet_hour=99, subnet_size=256)
        read = MagicMock(return_value=counts)
        with patch(f"{GATE}._containment_counts", read):
            action = _create(svc, "203.0.113.7", 0.99, human_only=True)
        read.assert_not_called()
        assert "approval.human_only=True" in action.reason

    def test_an_observing_action_never_pays_the_counts_read(self):
        svc = ApprovalService(config=ResponseConfig())
        counts = ContainmentCounts(tick=99, subnet_hour=99, subnet_size=256)
        read = MagicMock(return_value=counts)
        with patch(f"{GATE}._containment_counts", read):
            action = _create(
                svc, "203.0.113.7", 0.99, action_type=ActionType.EXECUTE_SPL_QUERY
            )
        read.assert_not_called()
        assert action.status == ActionStatus.APPROVED.value

    def test_an_invariant_outranks_the_quota_rule(self):
        # Both governors hold the row; the reason names the one that bound
        # first — the invariant is checked before the quota.
        svc = ApprovalService(config=ResponseConfig())
        rule = parse_entry(
            "ip:10.0.0.5", ORIGIN_ENV, reason="the floor", created_by="environment"
        )
        counts = ContainmentCounts(tick=99, subnet_hour=99, subnet_size=256)
        with (
            patch(f"{GATE}._active_protected_targets", return_value=(rule,)),
            patch(f"{GATE}._containment_counts", return_value=counts),
        ):
            action = _create(svc, "10.0.0.5", 0.99)
        assert "approval.protected_target=env:ip:10.0.0.5" in action.reason
        assert "response.max_containment_per_tick" not in action.reason

    def test_a_below_threshold_confidence_holds_for_its_own_rule(self):
        # The quota gates volume, not confidence: a row a person would have
        # been asked about anyway shows that rule, not a quota rule.
        svc = ApprovalService(config=ResponseConfig())
        counts = ContainmentCounts(tick=0, subnet_hour=0, subnet_size=256)
        with patch(f"{GATE}._containment_counts", return_value=counts):
            action = _create(svc, "203.0.113.7", 0.50)
        assert action.status == ActionStatus.PENDING.value
        assert "response.confidence_threshold=0.90 not met (0.50)" in action.reason


# --- the executor ------------------------------------------------------------


def _pending(
    action_id,
    *,
    target="203.0.113.7",
    action_type="waf_block",
    requires_approval=True,
    approved_by="alice",
):
    return PendingAction(
        action_id=action_id,
        action_type=action_type,
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

    def __init__(self, rows):
        self._rows = rows
        self.executed = []
        self.failed = []

    def list_actions(self, status=None, **_):
        return self._rows

    def protected_target_rules(self):
        from core.response.protected_targets import ProtectedTargetRules

        return ProtectedTargetRules()

    def breaker_hold(self):
        # The executor honors the breaker each tick; the fake declares it
        # armed, so its rows decide on their own merits.
        return None

    def mark_executed(self, action_id, result):
        self.executed.append(action_id)

    def mark_failed(self, action_id, error):
        self.failed.append(action_id)


def _executor(rows, config=ResponseConfig()):
    service = AutonomousResponseService.__new__(AutonomousResponseService)
    service.approval_service = _RulesService(rows)
    service.config = config
    service._execute_cloudflare_action = lambda **_: {"success": True}
    return service


class TestExecutorTicksContainment:
    def test_the_cap_plus_oneth_row_waits_for_the_next_tick(self):
        rows = [_pending(f"a-{i}") for i in range(3)]
        service = _executor(rows, ResponseConfig(max_containment_per_tick=2))
        results = service.execute_approved_actions()
        assert [r["action_id"] for r in results] == ["a-0", "a-1"]
        assert service.approval_service.executed == ["a-0", "a-1"]
        assert service.approval_service.failed == []

    def test_an_overflow_row_is_never_dropped_or_failed(self):
        # Not lost work: the row keeps its approved state and the next tick
        # picks it up.
        rows = [_pending(f"a-{i}") for i in range(3)]
        service = _executor(rows, ResponseConfig(max_containment_per_tick=2))
        service.execute_approved_actions()
        overflow = rows[2]
        assert overflow.status == "approved"
        assert overflow.executed_at is None
        assert overflow.action_id not in service.approval_service.failed

    def test_a_row_the_executor_does_not_attempt_consumes_no_allowance(self):
        # A containment type with no executor here (block_ip) is skipped for
        # another executor — it must not starve the tick's real attempts.
        rows = [
            _pending("a-query", action_type="block_ip"),
            _pending("a-waf-1"),
            _pending("a-waf-2"),
        ]
        service = _executor(rows, ResponseConfig(max_containment_per_tick=2))
        results = service.execute_approved_actions()
        # block_ip returns no result here — no executor in this service — so
        # it never enters the results list and never spends the allowance.
        assert [r["action_id"] for r in results] == ["a-waf-1", "a-waf-2"]
        assert service.approval_service.executed == ["a-waf-1", "a-waf-2"]

    def test_a_failed_attempt_still_spends_the_allowance(self):
        # The stub isolation always fails; the attempt was made, and the
        # world did change for it (a row marked failed). Volume is volume.
        rows = [
            _pending("a-iso-1", action_type="isolate_host"),
            _pending("a-iso-2", action_type="isolate_host"),
            _pending("a-waf", action_type="waf_block"),
        ]
        service = _executor(rows, ResponseConfig(max_containment_per_tick=2))
        results = service.execute_approved_actions()
        assert [r["action_id"] for r in results] == ["a-iso-1", "a-iso-2"]
        assert service.approval_service.failed == ["a-iso-1", "a-iso-2"]
        assert "a-waf" not in [r["action_id"] for r in results]

    def test_a_non_containment_row_is_unbounded_by_the_quota(self):
        rows = [
            _pending("a-spl", action_type="execute_spl_query"),
            _pending("a-spl-2", action_type="execute_spl_query"),
        ]
        service = _executor(rows, ResponseConfig(max_containment_per_tick=1))
        results = service.execute_approved_actions()
        # Observing types have no executor in this service: they pass the
        # quota check untouched and are left for another executor or a
        # person, unmarked.
        assert results == []
        assert service.approval_service.executed == []

    def test_the_default_config_allows_three_containment_attempts(self):
        rows = [_pending(f"a-{i}") for i in range(4)]
        service = _executor(rows)
        results = service.execute_approved_actions()
        assert [r["action_id"] for r in results] == ["a-0", "a-1", "a-2"]
        assert rows[3].status == "approved"


# --- restart safety is structural: counts are read, not accumulated ----------


def test_counts_come_from_the_rows_not_a_counter_table():
    # The gate reads one rolling-window query over approval_actions — the
    # rows are the counter, so a daemon restart cannot reset a quota.
    import inspect

    from core.response import approval_service

    source = inspect.getsource(approval_service._containment_counts)
    assert "ApprovalActionRow.created_at >=" in source
    assert "session.execute" in source


def test_no_quota_state_persists_between_ticks():
    # The executor's allowance is a loop-local counter rebuilt each pass.
    rows = [_pending(f"a-{i}") for i in range(2)]
    service = _executor(rows, ResponseConfig(max_containment_per_tick=1))
    first = service.execute_approved_actions()
    # A second pass over fresh rows gets a fresh allowance.
    rows_two = [_pending(f"b-{i}") for i in range(2)]
    service.approval_service = _RulesService(rows_two)
    second = service.execute_approved_actions()
    assert [r["action_id"] for r in first] == ["a-0"]
    assert [r["action_id"] for r in second] == ["b-0"]
