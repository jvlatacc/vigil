"""The speculative service: a decision becomes a ledger row, immediately.

Pins the idempotency behavior the spec demands end to end — dedupe while one
row is live, a fresh row after rollback (the widened index), expires_at from
the config TTL clamped to the ceiling — plus the commit-before-dispatch
ordering and the guard refusals. The throwaway database is session-scoped,
so every test uses its own target IP and never collides on the idempotency
key the service derives from type and target.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.response.approval_service import ActionStatus, ApprovalService
from core.response.config import ResponseConfig
from core.response.fastpath.adapters import (
    EnforcementRegistry,
    EnforceResult,
)
from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.policy import FastPathDecision
from core.response.fastpath.speculative_service import (
    FAST_PATH_ACTOR,
    SpeculativeActionService,
)
from core.storage.models import ApprovalAction
from core.storage.unit_of_work import unit_of_work

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]


def _target(n: int) -> str:
    return f"203.0.113.{n}"


def _config(**overrides) -> FastPathConfig:
    return FastPathConfig(enabled=True, **overrides)


def _decision(target: str, **overrides) -> FastPathDecision:
    values: dict[str, Any] = dict(
        action_type="rate_limit",
        target=target,
        ttl_seconds=600,
        rule="fast_path.review_threshold=0.85 met (0.92)",
        signals={
            "tier": "t1",
            "finding_id": f"f-{target}",
            "severity": "critical",
            "confidence": 0.92,
        },
    )
    values.update(overrides)
    return FastPathDecision(**values)


class _RecordingAdapter:
    """Counts apply calls and records what it saw; never touches a network."""

    simulates = False
    name = "recording"

    def __init__(self, result: EnforceResult | None = None, fail_times: int = 0):
        self.result = result or EnforceResult(True, "rs-1:rule-1", "enforced")
        self.fail_times = fail_times
        self.applies: list = []
        self.releases: list = []
        self.row_seen_at_apply = None

    def applies_to(self):
        return frozenset({"rate_limit", "tarpit", "session_pin", "latency_inject"})

    def apply(self, action):
        self.applies.append(action.action_id)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("connection reset")
        return self.result

    def release(self, action):
        self.releases.append(action.action_id)
        return EnforceResult(True, None, "released")


def _service(adapter=None, config=None):
    adapter = adapter or _RecordingAdapter()
    cfg = config or _config()
    registry = EnforcementRegistry(
        {action_type: adapter for action_type in cfg.allowed_action_types}
    )
    service = SpeculativeActionService(
        config=cfg,
        approvals=ApprovalService(config=ResponseConfig()),
        registry=registry,
    )
    return service, adapter


def _row(action_id: str) -> ApprovalAction:
    with unit_of_work() as session:
        row = session.get(ApprovalAction, action_id)
        assert row is not None
        return row


class TestInsertAndDispatch:
    def test_a_pass_inserts_a_speculative_row_and_dispatches_now(self):
        service, adapter = _service()
        outcome = service.create_speculative_action(_decision(_target(10)))
        assert outcome.inserted is True
        assert outcome.action.status == ActionStatus.SPECULATIVE.value
        assert outcome.action.created_by == FAST_PATH_ACTOR
        assert outcome.action.requires_approval is False
        assert outcome.action.reversibility == "reversible"
        assert adapter.applies == [outcome.action.action_id]

    def test_the_row_records_rule_signals_and_rollback_recipe(self):
        decision = _decision(_target(11))
        service, adapter = _service()
        outcome = service.create_speculative_action(decision)
        row = _row(outcome.action.action_id)
        assert row.parameters["speculative"] is True
        assert row.parameters["simulation"] is False
        assert row.parameters["rule"] == decision.rule
        assert row.parameters["signals"] == decision.signals
        assert row.parameters["ttl_seconds"] == 600
        assert row.parameters["rollback"]["adapter"] == "recording"
        assert row.parameters["rollback"]["action_type"] == "rate_limit"
        assert row.parameters["rollback"]["external_ref"] == "rs-1:rule-1"
        assert row.execution_result["applied"] is True
        assert row.execution_result["external_ref"] == "rs-1:rule-1"
        assert row.execution_result["simulated"] is False
        assert row.reason == decision.rule
        assert float(row.confidence) == 0.92
        assert row.evidence == ["finding:f-" + _target(11)]
        assert adapter.releases == []

    def test_a_t0_decision_records_zero_confidence_not_a_made_up_one(self):
        service, _ = _service()
        outcome = service.create_speculative_action(
            _decision(_target(12), signals={"tier": "t0", "finding_id": "f-12"})
        )
        assert float(outcome.action.confidence) == 0.0

    def test_the_row_is_committed_before_the_adapter_runs(self):
        class _ReadsAtApply(_RecordingAdapter):
            def apply(self, action):
                self.row_seen_at_apply = _row(action.action_id)
                return EnforceResult(True, "rs-1:rule-1", "enforced")

        service, adapter = _service(_ReadsAtApply())
        service.create_speculative_action(_decision(_target(13)))
        assert adapter.row_seen_at_apply is not None
        # A fresh session saw the row: the ledger committed before dispatch.
        assert adapter.row_seen_at_apply.status == ActionStatus.SPECULATIVE.value

    def test_a_simulated_dispatch_marks_the_row(self):
        class _Simulating(_RecordingAdapter):
            simulates = True
            name = "simulation"

            def apply(self, action):
                self.applies.append(action.action_id)
                return EnforceResult(True, None, "simulated rate_limit")

        service, adapter = _service(_Simulating())
        outcome = service.create_speculative_action(_decision(_target(14)))
        row = _row(outcome.action.action_id)
        assert row.parameters["simulation"] is True
        assert row.execution_result["simulated"] is True


class TestIdempotency:
    def test_a_live_row_is_returned_without_a_second_dispatch(self):
        service, adapter = _service()
        first = service.create_speculative_action(_decision(_target(20)))
        second = service.create_speculative_action(_decision(_target(20)))
        assert first.inserted is True
        assert second.inserted is False
        assert second.action.action_id == first.action.action_id
        assert adapter.applies == [first.action.action_id]

    def test_a_rolled_back_row_frees_the_key_for_a_fresh_row(self):
        service, adapter = _service()
        first = service.create_speculative_action(_decision(_target(21)))
        with unit_of_work() as session:
            row = session.get(ApprovalAction, first.action.action_id)
            row.status = ActionStatus.ROLLED_BACK.value
        second = service.create_speculative_action(_decision(_target(21)))
        assert second.inserted is True
        assert second.action.action_id != first.action.action_id
        assert second.action.status == ActionStatus.SPECULATIVE.value
        assert adapter.applies == [first.action.action_id, second.action.action_id]

    def test_an_adapter_exception_marks_the_row_failed_and_frees_the_key(self):
        service, _ = _service(_RecordingAdapter(fail_times=1))
        first = service.create_speculative_action(_decision(_target(22)))
        assert first.action.status == ActionStatus.FAILED.value
        assert first.action.execution_result["error"] == "adapter apply failed"
        # The failure freed the key: the next pass inserts a fresh row, and
        # with a recovered adapter it goes live speculative again.
        second = service.create_speculative_action(_decision(_target(22)))
        assert second.inserted is True
        assert second.action.action_id != first.action.action_id
        assert second.action.status == ActionStatus.SPECULATIVE.value

    def test_a_refused_apply_is_a_failed_row_never_a_live_one(self):
        service, _ = _service(
            _RecordingAdapter(
                EnforceResult(
                    False, None, "refused: cloudflare integration is disabled"
                )
            )
        )
        outcome = service.create_speculative_action(_decision(_target(23)))
        assert outcome.action.status == ActionStatus.FAILED.value
        assert "refused" in outcome.action.execution_result["error"]


class TestTtl:
    def test_expires_at_uses_the_configured_default_ttl(self):
        service, _ = _service(config=_config(default_ttl_seconds=600))
        before = datetime.now(timezone.utc)
        outcome = service.create_speculative_action(_decision(_target(30)))
        after = datetime.now(timezone.utc)
        row = _row(outcome.action.action_id)
        assert row.expires_at is not None
        assert before + timedelta(seconds=600) <= row.expires_at
        assert row.expires_at <= after + timedelta(seconds=600)
        assert row.parameters["ttl_seconds"] == 600

    def test_a_decision_ttl_above_the_ceiling_is_clamped(self):
        service, _ = _service(
            config=_config(default_ttl_seconds=600, max_ttl_seconds=1200)
        )
        outcome = service.create_speculative_action(
            _decision(_target(31), ttl_seconds=100000)
        )
        row = _row(outcome.action.action_id)
        assert row.parameters["ttl_seconds"] == 1200
        assert row.expires_at <= datetime.now(timezone.utc) + timedelta(seconds=1200)


class TestRefusals:
    def test_a_disabled_master_switch_refuses(self):
        service, adapter = _service(config=FastPathConfig(enabled=False))
        assert service.create_speculative_action(_decision(_target(40))) is None
        assert adapter.applies == []

    def test_an_action_type_outside_the_allowlist_refuses(self):
        service, adapter = _service()
        assert (
            service.create_speculative_action(
                _decision(_target(41), action_type="isolate_host")
            )
            is None
        )
        assert adapter.applies == []

    def test_a_non_routable_target_refuses(self):
        service, adapter = _service()
        for target in ("127.0.0.1", "not-an-address", "224.0.0.1"):
            assert service.create_speculative_action(_decision(target)) is None
        assert adapter.applies == []

    def test_the_per_target_cap_refuses_a_second_type(self):
        service, adapter = _service()
        first = service.create_speculative_action(_decision(_target(42)))
        assert first.inserted is True
        second = service.create_speculative_action(
            _decision(_target(42), action_type="tarpit")
        )
        assert second is None
        assert adapter.applies == [first.action.action_id]
