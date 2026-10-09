"""A breaker is a bet about shape: containment demand that looks like a storm
stops being automatic until a person says otherwise.

The breaker trips on volume, distinct-target churn, or executor failure rate
— never on any single action — and while tripped, containment rows wait for
a person at the gate and the executor skips them. An unreadable breaker
state holds containment for a person: an unreadable breaker must not read
as an armed one. A failed counts read cannot measure a storm and is
best-effort; the quota beside it fails closed on the same store.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from core.response.approval_service import (
    ActionStatus,
    ActionType,
    ApprovalService,
    PendingAction,
    Reversibility,
    breaker_state_hold,
    write_breaker_state,
)
from core.response.breaker import (
    BREAKER_CONFIG_KEY,
    BreakerCounts,
    BreakerState,
    breaker_decision,
    opened_state,
    parse_state,
    resume_due,
    tripped_state,
)
from core.response.config import ContainmentCounts, ResponseConfig
from core.time import utcnow

pytestmark = pytest.mark.unit

GATE = "core.response.approval_service"

TRIPPED = {
    "state": "tripped",
    "tripped_at": "2026-10-09T12:00:00",
    "reason": "response.breaker_distinct_targets=8 met (8)",
    "counts": {"volume_hour": 4, "distinct_targets_hour": 8, "failure_rate": 0.0},
    "auto_resume_at": None,
}


@pytest.fixture
def breaker_store():
    """Stand-in session and config store: the approval flag reads Act, the
    breaker's state reads armed, and nothing reaches PostgreSQL."""
    manager = MagicMock()

    @contextmanager
    def _scope():
        yield MagicMock()

    manager.session_scope = _scope
    config_store = MagicMock()
    config_store.read_system_config.return_value = {"enabled": False}
    config_store.set_system_config.return_value = True
    with (
        patch(f"{GATE}.get_db_manager", return_value=manager),
        patch(f"{GATE}.get_config_service", return_value=config_store),
    ):
        yield config_store


def _tripped_store():
    """A config store whose breaker key reads tripped and everything else
    reads Act."""
    store = MagicMock()

    def read(key):
        if key == BREAKER_CONFIG_KEY:
            return dict(TRIPPED)
        return {"enabled": False}

    store.read_system_config.side_effect = read
    store.set_system_config.return_value = True
    return store


# --- pure decision -----------------------------------------------------------


def test_a_volume_at_the_threshold_trips_with_its_rule():
    counts = BreakerCounts(
        volume_hour=10, distinct_targets_hour=1, failures=0, attempts=0
    )
    assert breaker_decision(counts, ResponseConfig()) == (
        "response.breaker_volume_threshold=10 met (10)"
    )


def test_distinct_target_churn_trips_the_rotating_ip_signature():
    # Volume well under the cap, targets never repeating: the storm a
    # per-target idempotency key cannot see.
    counts = BreakerCounts(
        volume_hour=4, distinct_targets_hour=8, failures=0, attempts=0
    )
    assert breaker_decision(counts, ResponseConfig()) == (
        "response.breaker_distinct_targets=8 met (8)"
    )


def test_a_half_failed_sample_trips_the_failure_rate():
    counts = BreakerCounts(
        volume_hour=1, distinct_targets_hour=1, failures=3, attempts=5
    )
    assert breaker_decision(counts, ResponseConfig()) == (
        "response.breaker_failure_rate=0.50 met (0.60)"
    )


def test_a_full_sample_that_stays_under_the_rate_allows():
    counts = BreakerCounts(
        volume_hour=1, distinct_targets_hour=1, failures=2, attempts=5
    )
    assert breaker_decision(counts, ResponseConfig()) is None


def test_an_incomplete_sample_never_trips_on_failure_rate():
    # 3 of 4 would read 75%, but the sample is 5: a rate over four attempts
    # is a rumor, not a signature.
    counts = BreakerCounts(
        volume_hour=1, distinct_targets_hour=1, failures=3, attempts=4
    )
    assert breaker_decision(counts, ResponseConfig()) is None


def test_a_fully_failing_sample_trips_immediately():
    counts = BreakerCounts(
        volume_hour=1, distinct_targets_hour=1, failures=5, attempts=5
    )
    assert breaker_decision(counts, ResponseConfig()) is not None


def test_a_quiet_signature_allows():
    counts = BreakerCounts(
        volume_hour=9, distinct_targets_hour=7, failures=2, attempts=5
    )
    assert breaker_decision(counts, ResponseConfig()) is None


def test_the_thresholds_are_the_operators_dials():
    counts = BreakerCounts(
        volume_hour=4, distinct_targets_hour=3, failures=0, attempts=0
    )
    config = ResponseConfig(breaker_volume_threshold=4)
    assert breaker_decision(counts, config) == (
        "response.breaker_volume_threshold=4 met (4)"
    )
    config = ResponseConfig(breaker_distinct_targets=3)
    assert breaker_decision(counts, config) == (
        "response.breaker_distinct_targets=3 met (3)"
    )


# --- the state a trip leaves behind ------------------------------------------


def test_a_trip_stamps_its_reason_and_counts():
    counts = BreakerCounts(
        volume_hour=4, distinct_targets_hour=8, failures=0, attempts=0
    )
    state = tripped_state(
        counts,
        "response.breaker_distinct_targets=8 met (8)",
        ResponseConfig(),
        utcnow(),
    )
    assert state.state == "tripped"
    assert state.reason == "response.breaker_distinct_targets=8 met (8)"
    assert state.counts["distinct_targets_hour"] == 8
    assert state.auto_resume_at is None  # manual reset is the default


def test_a_configured_cooldown_stamps_when_the_trip_ends():
    counts = BreakerCounts(
        volume_hour=10, distinct_targets_hour=1, failures=0, attempts=0
    )
    now = utcnow()
    state = tripped_state(
        counts,
        "response.breaker_volume_threshold=10 met (10)",
        ResponseConfig(breaker_auto_resume_minutes=30),
        now,
    )
    assert state.auto_resume_at == (now + timedelta(minutes=30)).isoformat()


def test_a_reset_clears_the_state_and_keeps_why():
    trip = tripped_state(
        BreakerCounts(volume_hour=10, distinct_targets_hour=1, failures=0, attempts=0),
        "response.breaker_volume_threshold=10 met (10)",
        ResponseConfig(),
        utcnow(),
    )
    opened = opened_state(trip, "alice", utcnow())
    assert opened.state == "open"
    assert opened.reset_by == "alice"
    assert opened.reason == trip.reason
    assert opened.tripped_at is None
    assert opened.reset_at is not None
    assert opened.auto_resume_at is None


def test_a_state_round_trips_through_the_store():
    now = utcnow()
    trip = tripped_state(
        BreakerCounts(volume_hour=10, distinct_targets_hour=1, failures=0, attempts=0),
        "response.breaker_volume_threshold=10 met (10)",
        ResponseConfig(breaker_auto_resume_minutes=15),
        now,
    )
    assert parse_state(trip.to_payload()) == trip


def test_an_absent_or_empty_state_reads_armed():
    assert parse_state(None).state == "open"
    assert parse_state({}).state == "open"
    assert parse_state({"enabled": False}).state == "open"


def test_an_unreadable_state_raises_and_the_caller_holds():
    with pytest.raises(ValueError):
        parse_state("tripped")
    with pytest.raises(ValueError):
        parse_state({"state": "bogus"})


# --- when a trip ends --------------------------------------------------------


def _trip(minutes_ago, cooldown=0):
    now = utcnow()
    state = BreakerState(
        state="tripped",
        tripped_at=(now - timedelta(minutes=minutes_ago)).isoformat(),
        reason="response.breaker_volume_threshold=10 met (10)",
        counts={"volume_hour": 10, "distinct_targets_hour": 1, "failure_rate": 0.0},
        auto_resume_at=None,
    )
    return state, ResponseConfig(breaker_auto_resume_minutes=cooldown)


def test_a_fresh_trip_does_not_resume_on_its_own():
    state, config = _trip(minutes_ago=10, cooldown=30)
    assert resume_due(state, config, utcnow()) is False


def test_a_cooldown_that_has_elapsed_resumes():
    state, config = _trip(minutes_ago=40, cooldown=30)
    assert resume_due(state, config, utcnow()) is True


def test_a_cooldown_of_zero_is_manual_reset_only():
    state, config = _trip(minutes_ago=10_000, cooldown=0)
    assert resume_due(state, config, utcnow()) is False


def test_a_trip_with_no_time_reference_never_resumes():
    # Fail closed: without a stamp there is no basis to call a cooldown over.
    state = BreakerState(
        state="tripped",
        tripped_at=None,
        reason="x",
        counts={},
        auto_resume_at=None,
    )
    config = ResponseConfig(breaker_auto_resume_minutes=30)
    assert resume_due(state, config, utcnow()) is False


def test_an_open_breaker_is_never_due():
    state = parse_state(None)
    assert (
        resume_due(state, ResponseConfig(breaker_auto_resume_minutes=30), utcnow())
        is False
    )


# --- the gate ----------------------------------------------------------------


def _create(
    svc: ApprovalService,
    target: str,
    confidence: float,
    action_type=ActionType.WAF_BLOCK,
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


def _quiet_quota():
    return ContainmentCounts(tick=0, subnet_hour=0, subnet_size=256)


@pytest.mark.usefixtures("breaker_store")
class TestGateTripsOnStormShape:
    def test_a_rotating_target_storm_trips_and_holds_the_row(self, breaker_store):
        svc = ApprovalService(config=ResponseConfig())
        counts = BreakerCounts(
            volume_hour=4, distinct_targets_hour=8, failures=0, attempts=0
        )
        with (
            patch(f"{GATE}._containment_counts", return_value=_quiet_quota()),
            patch(f"{GATE}._breaker_counts", return_value=counts),
        ):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.PENDING.value
        assert "response.breaker_distinct_targets=8 met (8)" in action.reason

    def test_the_trip_is_persisted_before_the_row_is_decided(self, breaker_store):
        svc = ApprovalService(config=ResponseConfig())
        counts = BreakerCounts(
            volume_hour=10, distinct_targets_hour=2, failures=0, attempts=0
        )
        with (
            patch(f"{GATE}._containment_counts", return_value=_quiet_quota()),
            patch(f"{GATE}._breaker_counts", return_value=counts),
        ):
            _create(svc, "203.0.113.7", 0.99)
        breaker_store.set_system_config.assert_called_once()
        key = breaker_store.set_system_config.call_args[0][0]
        payload = breaker_store.set_system_config.call_args[0][1]
        assert key == BREAKER_CONFIG_KEY
        assert payload["state"] == "tripped"
        assert payload["counts"]["volume_hour"] == 10

    def test_while_tripped_the_next_row_holds_without_measuring(self, breaker_store):
        # A trip binds every process at once: the next row reads the state,
        # sees tripped, and waits — no counts query, no second trip log.
        store = _tripped_store()
        breaker_store.read_system_config.side_effect = (
            store.read_system_config.side_effect
        )
        svc = ApprovalService(config=ResponseConfig())
        counts = MagicMock()
        with (
            patch(f"{GATE}._containment_counts", return_value=_quiet_quota()),
            patch(f"{GATE}._breaker_counts", counts),
        ):
            action = _create(svc, "203.0.113.8", 0.99)
        counts.assert_not_called()
        assert action.status == ActionStatus.PENDING.value
        assert "response.breaker_state=tripped" in action.reason

    def test_a_failed_state_read_holds_containment_for_a_person(self, breaker_store):
        def read(key):
            if key == BREAKER_CONFIG_KEY:
                raise RuntimeError("db down")
            return {"enabled": False}

        breaker_store.read_system_config.side_effect = read
        svc = ApprovalService(config=ResponseConfig())
        with (
            patch(f"{GATE}._containment_counts", return_value=_quiet_quota()),
            patch(f"{GATE}._breaker_counts", MagicMock()),
        ):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.PENDING.value
        assert "response.breaker_state=read_failed" in action.reason

    def test_an_armed_breaker_auto_approves(self, breaker_store):
        svc = ApprovalService(config=ResponseConfig())
        counts = BreakerCounts(
            volume_hour=1, distinct_targets_hour=1, failures=0, attempts=5
        )
        with (
            patch(f"{GATE}._containment_counts", return_value=_quiet_quota()),
            patch(f"{GATE}._breaker_counts", return_value=counts),
        ):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.APPROVED.value

    def test_a_failed_counts_read_cannot_measure_a_storm(self, breaker_store):
        # Best-effort by design: the quota beside it fails closed on the
        # same store, so an unreadable history holds the row anyway.
        svc = ApprovalService(config=ResponseConfig())
        with (
            patch(f"{GATE}._containment_counts", return_value=_quiet_quota()),
            patch(f"{GATE}._breaker_counts", side_effect=RuntimeError("db down")),
        ):
            action = _create(svc, "203.0.113.7", 0.99)
        assert action.status == ActionStatus.APPROVED.value

    def test_a_row_the_quota_held_never_pays_the_state_read(self, breaker_store):
        # The breaker refines nothing about a row already waiting for a
        # person: reading state could only change the rule string.
        svc = ApprovalService(config=ResponseConfig())
        held = ContainmentCounts(tick=3, subnet_hour=0, subnet_size=256)
        with patch(f"{GATE}._containment_counts", return_value=held):
            action = _create(svc, "203.0.113.7", 0.99)
        assert "response.max_containment_per_tick" in action.reason
        assert "response.breaker" not in action.reason

    def test_an_observing_action_never_pays_the_breaker_read(self, breaker_store):
        svc = ApprovalService(config=ResponseConfig())
        counts = MagicMock()
        with patch(f"{GATE}._breaker_counts", counts):
            action = _create(
                svc, "203.0.113.7", 0.99, action_type=ActionType.EXECUTE_SPL_QUERY
            )
        counts.assert_not_called()
        assert action.status == ActionStatus.APPROVED.value

    def test_an_invariant_outranks_the_breaker_rule(self, breaker_store):
        # Both governors hold the row; the reason names the one that bound
        # first — the invariant is checked before the breaker.
        from core.response.protected_targets import ORIGIN_ENV, parse_entry

        rule = parse_entry(
            "ip:10.0.0.5", ORIGIN_ENV, reason="the floor", created_by="environment"
        )
        svc = ApprovalService(config=ResponseConfig())
        counts = BreakerCounts(
            volume_hour=10, distinct_targets_hour=8, failures=0, attempts=0
        )
        with (
            patch(f"{GATE}._active_protected_targets", return_value=(rule,)),
            patch(f"{GATE}._containment_counts", return_value=_quiet_quota()),
            patch(f"{GATE}._breaker_counts", return_value=counts),
        ):
            action = _create(svc, "10.0.0.5", 0.99)
        assert "approval.protected_target=env:ip:10.0.0.5" in action.reason
        assert "response.breaker" not in action.reason


# --- the breaker's verdict on a row about to execute --------------------------


def _approved(
    action_id,
    *,
    target="203.0.113.7",
    action_type="waf_block",
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
        requires_approval=False,
        status="approved",
        approved_by="responder",
    )


class _BreakerService:
    """Executor stand-in: rows in, a breaker verdict on call."""

    def __init__(self, rows, verdict):
        self._rows = rows
        self._verdict = verdict
        self.executed = []
        self.failed = []

    def list_actions(self, status=None, **_):
        return self._rows

    def protected_target_rules(self):
        from core.response.protected_targets import ProtectedTargetRules

        return ProtectedTargetRules()

    def breaker_hold(self):
        return self._verdict

    def mark_executed(self, action_id, result):
        self.executed.append(action_id)

    def mark_failed(self, action_id, error):
        self.failed.append(action_id)


def _executor(rows, verdict):
    from core.response.autonomous_response_service import (
        AutonomousResponseService,
    )

    service = AutonomousResponseService.__new__(AutonomousResponseService)
    service.approval_service = _BreakerService(rows, verdict)
    service.config = ResponseConfig()
    service._execute_cloudflare_action = lambda **_: {"success": True}
    return service


class TestExecutorHonorsTheBreaker:
    def test_while_tripped_no_containment_row_executes(self):
        rows = [_approved(f"a-{i}") for i in range(3)]
        service = _executor(rows, "response.breaker_state=tripped")
        assert service.execute_approved_actions() == []
        assert service.approval_service.executed == []
        assert service.approval_service.failed == []

    def test_a_skipped_row_stays_approved_for_the_reset(self):
        # Not lost work: the row keeps its approval and executes the tick
        # after a person resets the breaker.
        row = _approved("a-1")
        service = _executor([row], "response.breaker_state=tripped")
        service.execute_approved_actions()
        assert row.status == "approved"
        assert row.executed_at is None

    def test_an_armed_breaker_executes_normally(self):
        rows = [_approved("a-1"), _approved("a-2")]
        service = _executor(rows, None)
        results = service.execute_approved_actions()
        assert [r["action_id"] for r in results] == ["a-1", "a-2"]
        assert service.approval_service.executed == ["a-1", "a-2"]

    def test_an_unreadable_breaker_holds_the_row(self):
        # Fail-closed: a read failure is not an armed breaker.
        rows = [_approved("a-1")]
        service = _executor(rows, "response.breaker_state=read_failed")
        assert service.execute_approved_actions() == []
        assert service.approval_service.failed == []


# --- transitions are announced exactly once ----------------------------------


class TestTransitionLogging:
    def test_a_trip_is_announced_once_when_it_is_saved(self, breaker_store, caplog):
        import logging

        trip = tripped_state(
            BreakerCounts(
                volume_hour=10, distinct_targets_hour=2, failures=0, attempts=0
            ),
            "response.breaker_volume_threshold=10 met (10)",
            ResponseConfig(),
            utcnow(),
        )
        with caplog.at_level(logging.WARNING):
            assert write_breaker_state(trip) is True
        trips = [r for r in caplog.records if "TRIPPED" in r.message]
        assert len(trips) == 1
        assert "response.breaker_volume_threshold=10 met (10)" in trips[0].message

    def test_a_reset_is_announced_once_with_its_operator(self, breaker_store, caplog):
        import logging

        trip = tripped_state(
            BreakerCounts(
                volume_hour=10, distinct_targets_hour=2, failures=0, attempts=0
            ),
            "response.breaker_volume_threshold=10 met (10)",
            ResponseConfig(),
            utcnow(),
        )
        opened = opened_state(trip, "alice", utcnow())
        with caplog.at_level(logging.INFO):
            assert write_breaker_state(opened) is True
        openings = [r for r in caplog.records if "OPENED" in r.message]
        assert len(openings) == 1
        assert "alice" in openings[0].message

    def test_a_failed_state_write_holds_and_says_so(self, breaker_store, caplog):
        import logging

        breaker_store.set_system_config.return_value = False
        trip = tripped_state(
            BreakerCounts(
                volume_hour=10, distinct_targets_hour=2, failures=0, attempts=0
            ),
            "response.breaker_volume_threshold=10 met (10)",
            ResponseConfig(),
            utcnow(),
        )
        with caplog.at_level(logging.ERROR):
            assert write_breaker_state(trip) is False
        assert any("holding containment" in r.message for r in caplog.records)


# --- the persisted verdict a row reads ---------------------------------------


class TestBreakerStateHold:
    def test_a_tripped_state_holds_the_row(self):
        store = _tripped_store()
        with patch(f"{GATE}.get_config_service", return_value=store):
            assert breaker_state_hold(ResponseConfig()) == (
                "response.breaker_state=tripped"
            )

    def test_an_elapsed_cooldown_persists_the_open_before_releasing(self):
        store = MagicMock()
        store.set_system_config.return_value = True

        def read(key):
            if key == BREAKER_CONFIG_KEY:
                stale = dict(TRIPPED)
                stale["auto_resume_at"] = (utcnow() - timedelta(minutes=1)).isoformat()
                return stale
            return {"enabled": False}

        store.read_system_config.side_effect = read
        with patch(f"{GATE}.get_config_service", return_value=store):
            verdict = breaker_state_hold(ResponseConfig(breaker_auto_resume_minutes=30))
        assert verdict is None
        payload = store.set_system_config.call_args[0][1]
        assert payload["state"] == "open"
        assert payload["reset_by"] == "auto-resume"

    def test_a_future_resume_stamp_waits(self):
        store = MagicMock()
        store.set_system_config.return_value = True

        def read(key):
            if key == BREAKER_CONFIG_KEY:
                fresh = dict(TRIPPED)
                fresh["auto_resume_at"] = (utcnow() + timedelta(minutes=5)).isoformat()
                return fresh
            return {"enabled": False}

        store.read_system_config.side_effect = read
        with patch(f"{GATE}.get_config_service", return_value=store):
            verdict = breaker_state_hold(ResponseConfig(breaker_auto_resume_minutes=30))
        assert verdict == "response.breaker_state=tripped"
        store.set_system_config.assert_not_called()

    def test_a_failed_resume_write_waits_for_a_person(self):
        store = MagicMock()
        store.set_system_config.return_value = False

        def read(key):
            if key == BREAKER_CONFIG_KEY:
                stale = dict(TRIPPED)
                stale["auto_resume_at"] = (utcnow() - timedelta(minutes=1)).isoformat()
                return stale
            return {"enabled": False}

        store.read_system_config.side_effect = read
        with patch(f"{GATE}.get_config_service", return_value=store):
            verdict = breaker_state_hold(ResponseConfig(breaker_auto_resume_minutes=30))
        assert verdict == "response.breaker_state=resume_write_failed"

    def test_an_unreadable_state_holds_even_outside_the_gate(self):
        store = MagicMock()
        store.read_system_config.side_effect = RuntimeError("db down")
        with patch(f"{GATE}.get_config_service", return_value=store):
            assert breaker_state_hold(ResponseConfig()) == (
                "response.breaker_state=read_failed"
            )


# --- restart safety is structural: counts are read, not accumulated ----------


def test_the_signature_is_read_from_the_rows_not_a_counter():
    # The gate measures one rolling-window query per decision — the rows
    # are the counter, so a daemon restart cannot reset a storm.
    import inspect

    from core.response import approval_service

    source = inspect.getsource(approval_service._breaker_counts)
    assert "ApprovalActionRow.created_at >=" in source
    assert "session.execute" in source


# --- replay: the breaker's holds, re-decided from the rows -------------------


def _replay_row(i, minute, *, target=None, status="executed"):
    from services.daemon.intent import ReplayApproval

    return ReplayApproval(
        id=f"a-{i}",
        confidence=0.99,
        reversibility=Reversibility.REVERSIBLE,
        action_type="waf_block",
        target=target or f"203.0.113.{i}",
        status=status,
        created_at=datetime(2026, 10, 9, 12, 0, 0) + timedelta(minutes=minute),
    )


class TestReplayBreakerHolds:
    def test_a_rotating_target_storm_trips_on_churn_in_replay(self):
        from services.daemon.intent import breaker_holds

        rows = [_replay_row(i, i, target=f"203.0.113.{i}") for i in range(9)]
        quotas = [None] * len(rows)
        holds = breaker_holds(rows, ResponseConfig(), quotas)
        assert all(h is None for h in holds[:7])
        assert holds[7] == "response.breaker_distinct_targets=8 met (8)"
        # Manual reset is the default: the trip holds the rest of the window.
        assert holds[8] == "response.breaker_state=tripped"

    def test_repeated_targets_do_not_churn_the_breaker(self):
        from services.daemon.intent import breaker_holds

        rows = [_replay_row(i, i, target="203.0.113.7") for i in range(9)]
        quotas = [None] * len(rows)
        holds = breaker_holds(rows, ResponseConfig(), quotas)
        assert all(h is None for h in holds)

    def test_a_row_the_quota_held_never_measures_the_storm(self):
        from services.daemon.intent import breaker_holds

        rows = [_replay_row(i, i, target=f"203.0.113.{i}") for i in range(9)]
        quotas = [None] * 7 + ["response.max_containment_per_tick=3 met (3)", None]
        holds = breaker_holds(rows, ResponseConfig(), quotas)
        assert holds[7] is None  # quota-held: the breaker is not consulted
        assert holds[8] == "response.breaker_distinct_targets=8 met (9)"

    def test_a_cooldown_expires_and_the_breaker_re_arms(self):
        from services.daemon.intent import breaker_holds

        rows = [
            _replay_row(0, 0, target="203.0.113.0"),
            _replay_row(1, 10, target="203.0.113.1"),
            _replay_row(2, 20, target="203.0.113.2"),
            _replay_row(3, 65, target="203.0.113.2"),
        ]
        config = ResponseConfig(
            breaker_distinct_targets=3, breaker_auto_resume_minutes=30
        )
        quotas = [None] * len(rows)
        holds = breaker_holds(rows, config, quotas)
        assert holds[1] is None
        assert holds[2] == "response.breaker_distinct_targets=3 met (3)"
        assert holds[3] is None  # the 30-minute cooldown elapsed at :50

    def test_a_rejected_row_counts_toward_nothing(self):
        from services.daemon.intent import breaker_holds

        rows = [
            _replay_row(0, 0, target="203.0.113.0", status="rejected"),
            _replay_row(1, 1, target="203.0.113.1"),
            _replay_row(2, 2, target="203.0.113.2"),
        ]
        quotas = [None] * len(rows)
        holds = breaker_holds(rows, ResponseConfig(breaker_distinct_targets=2), quotas)
        assert holds[0] is None
        assert holds[1] is None
        assert holds[2] == "response.breaker_distinct_targets=2 met (2)"

    def test_a_rejected_row_is_never_held_by_the_breaker(self):
        from services.daemon.intent import breaker_holds

        rows = [
            _replay_row(0, 0, target="203.0.113.0", status="rejected"),
            _replay_row(1, 1, target="203.0.113.1"),
            _replay_row(2, 2, target="203.0.113.2"),
        ]
        config = ResponseConfig(breaker_distinct_targets=2)
        quotas = [None] * len(rows)
        holds = breaker_holds(rows, config, quotas)
        # A person's no is not the daemon's volume: it is not held, and the
        # trip on row 2 counts 2 distinct targets, not 3.
        assert holds == [
            None,
            None,
            "response.breaker_distinct_targets=2 met (2)",
        ]


# --- the shipped knobs read what they declare --------------------------------


def test_the_default_breaker_is_armed_and_manual_reset_only():
    svc = ApprovalService(config=ResponseConfig())
    assert svc.config.breaker_volume_threshold == 10
    assert svc.config.breaker_distinct_targets == 8
    assert svc.config.breaker_failure_rate == 0.50
    assert svc.config.breaker_auto_resume_minutes == 0
