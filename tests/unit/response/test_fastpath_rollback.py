"""The rollback service: release, escalate, expire.

Pins the three verbs end to end against the throwaway database: the release
verb drives the adapter's release and marks the row ``rolled_back`` (freeing
the idempotency key, so the target can be restricted again); escalation
routes through the unmodified approval pipeline and never executes the full
action itself; the TTL sweep releases whatever is past expiry regardless of
adjudication state, claims each row exactly once under concurrency, and
leaves a failed release live for the next tick.

Distinct targets per test: the throwaway database is session-scoped, so
tests share it in arbitrary order and a reused idempotency key would
collide with itself.
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
from core.response.fastpath.rollback import (
    ESCALATION_LINK_FIELD,
    RELEASE_REASON_ADJUDICATED,
    RELEASE_REASON_FIELD,
    RELEASE_REASON_HUMAN,
    RELEASE_REASON_TTL_EXPIRED,
    SOURCE_ADJUDICATOR,
    SOURCE_HUMAN,
    TTL_SWEEP_ACTOR,
    EscalationRequest,
    RollbackService,
)
from core.response.fastpath.speculative_service import (
    SpeculativeActionService,
    speculative_key,
)
from core.storage.models import ApprovalAction
from core.storage.unit_of_work import unit_of_work

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]


@pytest.fixture(autouse=True)
def _leave_no_live_speculative_rows():
    """Resolve every speculative row this test leaves behind.

    The throwaway database is shared across the session and every file
    draws from the same target space: a live speculative row left behind
    would dedupe the next file's creation for the same target and fail it
    mysteriously. Finalization runs even when the test itself failed, so
    the leak cannot survive a red run either.
    """
    yield
    with unit_of_work() as session:
        session.query(ApprovalAction).filter(
            ApprovalAction.status == ActionStatus.SPECULATIVE.value
        ).update({ApprovalAction.status: ActionStatus.ROLLED_BACK.value})


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
    """Counts apply and release calls; never touches a network.

    ``release_result`` is the answer every release gives, ``fail_release``
    makes release raise (the vendor-unreachable shape the sweep must
    survive), and ``on_release`` — if set — runs once inside the first
    release call, the hook the interleaved-sweep test drives its second
    sweep through.
    """

    simulates = False
    name = "recording"

    def __init__(self):
        self.applies: list = []
        self.releases: list = []
        self.release_result = EnforceResult(True, None, "released")
        self.fail_release = False
        self.on_release = None

    def applies_to(self):
        return frozenset({"rate_limit", "tarpit", "session_pin", "latency_inject"})

    def apply(self, action):
        self.applies.append(action.action_id)
        return EnforceResult(True, "rs-1:rule-1", "enforced")

    def release(self, action):
        self.releases.append(action.action_id)
        hook = self.on_release
        self.on_release = None
        if hook is not None:
            hook()
        if self.fail_release:
            raise RuntimeError("vendor unreachable")
        return self.release_result


def _services(adapter=None, config=None):
    """A speculative service and a rollback service sharing one adapter."""
    adapter = adapter or _RecordingAdapter()
    cfg = config or _config()
    registry = EnforcementRegistry(
        {action_type: adapter for action_type in cfg.allowed_action_types}
    )
    speculative = SpeculativeActionService(
        config=cfg,
        approvals=ApprovalService(config=ResponseConfig()),
        registry=registry,
    )
    rollback = RollbackService(
        config=cfg,
        approvals=ApprovalService(config=ResponseConfig()),
        registry=registry,
    )
    return speculative, rollback, adapter


def _live_row(action_id: str) -> ApprovalAction:
    with unit_of_work() as session:
        row = session.get(ApprovalAction, action_id)
        assert row is not None
        session.expunge(row)
        return row


def _expire_row(action_id: str, seconds_ago: int = 5) -> None:
    """Back-date a row's expiry so the sweep must release it."""
    with unit_of_work() as session:
        row = session.get(ApprovalAction, action_id)
        assert row is not None
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)


def _make_speculative(target: str, **config_overrides):
    speculative, rollback, adapter = _services(config=_config(**config_overrides))
    outcome = speculative.create_speculative_action(_decision(target))
    assert outcome is not None and outcome.inserted
    return outcome.action.action_id, rollback, adapter


class TestExpire:
    def test_the_sweep_releases_an_expired_row_whatever_adjudication_is_doing(self):
        action_id, rollback, adapter = _make_speculative(_target(31))
        # An adjudication in flight, as far as the row can say: an open
        # marker on the parameters. The sweep reads status and expiry only.
        with unit_of_work() as session:
            row = session.get(ApprovalAction, action_id)
            row.parameters = {
                **(row.parameters or {}),
                "adjudication": {"run_id": "run-1", "state": "executing"},
            }
        _expire_row(action_id)

        outcome = rollback.expire()

        assert outcome.examined == 1
        assert outcome.released == 1
        row = _live_row(action_id)
        assert row.status == ActionStatus.ROLLED_BACK.value
        assert row.execution_result["reason"] == RELEASE_REASON_TTL_EXPIRED
        assert row.execution_result["actor"] == TTL_SWEEP_ACTOR
        assert adapter.releases == [action_id]

    def test_the_sweep_leaves_rows_that_are_still_live(self):
        action_id, rollback, adapter = _make_speculative(_target(32))

        outcome = rollback.expire()

        assert outcome.examined == 0
        assert outcome.released == 0
        assert _live_row(action_id).status == ActionStatus.SPECULATIVE.value
        assert adapter.releases == []

    def test_the_sweep_is_idempotent(self):
        action_id, rollback, adapter = _make_speculative(_target(33))
        _expire_row(action_id)
        assert rollback.expire().released == 1

        again = rollback.expire()

        assert again.examined == 0
        assert again.released == 0
        assert adapter.releases == [action_id]
        assert _live_row(action_id).status == ActionStatus.ROLLED_BACK.value

    def test_a_failed_release_stays_speculative_for_the_next_sweep(self):
        action_id, rollback, adapter = _make_speculative(_target(34))
        _expire_row(action_id)
        adapter.fail_release = True

        failed = rollback.expire()

        assert failed.released == 0
        assert _live_row(action_id).status == ActionStatus.SPECULATIVE.value

        adapter.fail_release = False
        retried = rollback.expire()

        assert retried.released == 1
        assert _live_row(action_id).status == ActionStatus.ROLLED_BACK.value
        assert adapter.releases == [action_id, action_id]

    def test_the_sweep_honors_the_batch_bound(self):
        first, rollback, _ = _make_speculative(_target(35))
        second, _, _ = _make_speculative(_target(36))
        third, _, _ = _make_speculative(_target(37))
        for action_id in (first, second, third):
            _expire_row(action_id)

        bounded = rollback.expire(batch=2)
        remainder = rollback.expire(batch=2)

        assert bounded.examined == 2 and bounded.released == 2
        assert remainder.examined == 1 and remainder.released == 1
        assert _live_row(third).status == ActionStatus.ROLLED_BACK.value

    def test_interleaved_sweeps_release_a_row_exactly_once(self):
        action_id, rollback, adapter = _make_speculative(_target(38))
        _expire_row(action_id)
        # The second sweep starts inside the first one's adapter call — the
        # release-then-claim ordering means both see the row live, both call
        # the idempotent release, and the guarded claim lets exactly one
        # mark it.
        inner = RollbackService(
            config=rollback.config,
            approvals=ApprovalService(config=ResponseConfig()),
            registry=rollback.registry,
        )
        adapter.on_release = lambda: inner.expire()

        rollback.expire()

        row = _live_row(action_id)
        assert row.status == ActionStatus.ROLLED_BACK.value
        # The vendor was called by both racers (its release is idempotent),
        # but the row carries exactly one release record.
        assert adapter.releases == [action_id, action_id]
        assert row.reason.count(RELEASE_REASON_FIELD) == 1
        assert row.execution_result["released"] is True


class TestRelease:
    def test_release_drives_the_adapter_and_marks_the_row(self):
        action_id, rollback, adapter = _make_speculative(_target(41))

        outcome = rollback.release(
            action_id, RELEASE_REASON_ADJUDICATED, "adjudicate-run-1"
        )

        assert outcome.released is True
        assert adapter.releases == [action_id]
        row = _live_row(action_id)
        assert row.status == ActionStatus.ROLLED_BACK.value
        assert row.reason.endswith(
            f"{RELEASE_REASON_FIELD}={RELEASE_REASON_ADJUDICATED}"
        )
        assert row.execution_result["released"] is True
        assert row.execution_result["reason"] == RELEASE_REASON_ADJUDICATED
        assert row.execution_result["actor"] == "adjudicate-run-1"
        assert row.execution_result["adapter"] == "recording"
        # The rollback recipe survives: it is the release's provenance.
        assert row.parameters["rollback"]["action_type"] == "rate_limit"

    def test_a_released_target_can_be_restricted_again(self):
        target = _target(42)
        speculative, rollback, _ = _services()
        first = speculative.create_speculative_action(_decision(target))
        assert first is not None and first.inserted

        rollback.release(
            first.action.action_id, RELEASE_REASON_ADJUDICATED, "adjudicate-run-1"
        )
        second = speculative.create_speculative_action(_decision(target))

        assert second is not None
        assert second.inserted is True
        assert second.action.action_id != first.action.action_id
        assert second.action.status == ActionStatus.SPECULATIVE.value
        assert second.action.idempotency_key == speculative_key("rate_limit", target)

    def test_release_refuses_a_row_that_is_not_speculative(self):
        action_id, rollback, adapter = _make_speculative(_target(43))
        assert (
            rollback.release(action_id, RELEASE_REASON_HUMAN, "analyst-1").released
            is True
        )

        second = rollback.release(action_id, RELEASE_REASON_HUMAN, "analyst-1")

        assert second.released is False
        assert "not speculative" in second.detail
        assert adapter.releases == [action_id]
        assert _live_row(action_id).status == ActionStatus.ROLLED_BACK.value

    def test_a_failed_adapter_release_leaves_the_row_live(self):
        action_id, rollback, adapter = _make_speculative(_target(44))
        adapter.release_result = EnforceResult(False, None, "refused: vendor down")

        outcome = rollback.release(
            action_id, RELEASE_REASON_TTL_EXPIRED, TTL_SWEEP_ACTOR
        )

        assert outcome.released is False
        assert "refused: vendor down" in outcome.detail
        row = _live_row(action_id)
        assert row.status == ActionStatus.SPECULATIVE.value
        # The refusal stamped nothing: execution_result still carries the
        # apply record from dispatch, with no release fields on it.
        assert row.execution_result["applied"] is True
        assert "released" not in row.execution_result

    def test_release_rejects_an_unknown_reason(self):
        action_id, rollback, _ = _make_speculative(_target(45))
        with pytest.raises(ValueError):
            rollback.release(action_id, "because", "whoever")


class TestEscalate:
    def test_an_adjudicated_escalation_lands_pending_and_never_executes(self):
        target = _target(51)
        action_id, rollback, _ = _make_speculative(target)

        outcome = rollback.escalate(
            action_id,
            EscalationRequest(
                action_type="waf_block",
                target=target,
                confidence=0.5,
                reasoning="Rate-limited source matches credential stuffing.",
            ),
            decided_by="adjudicate-run-1",
            source=SOURCE_ADJUDICATOR,
        )

        assert outcome.escalated is True
        full = outcome.full_action
        assert full is not None
        assert full.action_type == "waf_block"
        assert full.status == ActionStatus.PENDING.value
        assert full.requires_approval is True
        assert full.approved_by is None
        assert full.executed_at is None
        row = _live_row(action_id)
        assert row.status == ActionStatus.ESCALATED.value
        assert row.reason.count(f"{ESCALATION_LINK_FIELD}={full.action_id}") == 1
        assert row.parameters["escalation"]["action_id"] == full.action_id
        assert row.parameters["escalation"]["source"] == SOURCE_ADJUDICATOR

    def test_a_human_escalation_records_the_persons_decision(self):
        target = _target(52)
        action_id, rollback, _ = _make_speculative(target)

        outcome = rollback.escalate(
            action_id,
            EscalationRequest(
                action_type="waf_block",
                target=target,
                confidence=0.92,
                reasoning="Confirmed by the analyst.",
            ),
            decided_by="analyst-1",
            source=SOURCE_HUMAN,
        )

        assert outcome.escalated is True
        full = outcome.full_action
        assert full is not None
        assert full.status == ActionStatus.APPROVED.value
        assert full.approved_by == "analyst-1"
        # Execution stays the approved-action executor's job; the escalation
        # itself never executes anything.
        assert full.executed_at is None

    def test_escalation_refuses_a_speculative_micro_action_type(self):
        action_id, rollback, _ = _make_speculative(_target(53))

        outcome = rollback.escalate(
            action_id,
            EscalationRequest(
                action_type="tarpit",
                target=_target(53),
                confidence=0.9,
                reasoning="a loop, not an escalation",
            ),
            decided_by="adjudicate-run-1",
            source=SOURCE_ADJUDICATOR,
        )

        assert outcome.escalated is False
        assert outcome.full_action is None
        assert "micro-action" in outcome.detail
        assert _live_row(action_id).status == ActionStatus.SPECULATIVE.value

    def test_escalation_of_an_unknown_type_is_refused(self):
        action_id, rollback, _ = _make_speculative(_target(54))

        outcome = rollback.escalate(
            action_id,
            EscalationRequest(
                action_type="block_everything",
                target=_target(54),
                confidence=0.9,
                reasoning="not a real action type",
            ),
            decided_by="adjudicate-run-1",
            source=SOURCE_ADJUDICATOR,
        )

        assert outcome.escalated is False
        assert outcome.full_action is None
        assert _live_row(action_id).status == ActionStatus.SPECULATIVE.value

    def test_escalation_refuses_a_row_already_resolved(self):
        action_id, rollback, _ = _make_speculative(_target(55))
        rollback.release(action_id, RELEASE_REASON_HUMAN, "analyst-1")

        outcome = rollback.escalate(
            action_id,
            EscalationRequest(
                action_type="waf_block",
                target=_target(55),
                confidence=0.9,
                reasoning="too late",
            ),
            decided_by="analyst-1",
            source=SOURCE_HUMAN,
        )

        assert outcome.escalated is False
        assert outcome.full_action is None
        assert "not speculative" in outcome.detail

    def test_escalation_rejects_an_unknown_source(self):
        action_id, rollback, _ = _make_speculative(_target(56))
        with pytest.raises(ValueError):
            rollback.escalate(
                action_id,
                EscalationRequest(
                    action_type="waf_block",
                    target=_target(56),
                    confidence=0.9,
                    reasoning="who asked?",
                ),
                decided_by="whoever",
                source="the shadow",
            )

    def test_the_sweep_does_not_touch_an_escalated_row(self):
        target = _target(57)
        action_id, rollback, adapter = _make_speculative(target)
        outcome = rollback.escalate(
            action_id,
            EscalationRequest(
                action_type="waf_block",
                target=target,
                confidence=0.9,
                reasoning="escalated before its TTL",
            ),
            decided_by="adjudicate-run-1",
            source=SOURCE_ADJUDICATOR,
        )
        assert outcome.escalated is True
        _expire_row(action_id)

        sweep = rollback.expire()

        assert sweep.examined == 0
        assert adapter.releases == []
        assert _live_row(action_id).status == ActionStatus.ESCALATED.value
