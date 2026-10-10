"""The review seam: verdicts applied, once, and never against a resolved row.

Pins the three verdict behaviors end to end against the throwaway
database — release marks ``rolled_back``, escalate creates the full
containment through the unmodified approval pipeline and marks
``escalated``, retain extends ``expires_at`` exactly once and clamps to
the ceiling — and the authority rule: a human decision, the TTL sweep or
an earlier verdict resolves the row first, and the late verdict is
recorded on the run row (``verdict_status`` superseded, the resolver
named) and changes nothing else.

Distinct targets per test, as in the rollback suite: the throwaway
database is session-scoped and a live speculative row dedupes by target.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from core.response.approval_service import ActionStatus, ApprovalService
from core.response.config import ResponseConfig
from core.response.fastpath.adapters import EnforcementRegistry, EnforceResult
from core.response.fastpath.adjudication import (
    VERDICT_ESCALATE,
    VERDICT_PENDING,
    VERDICT_RELEASE,
    VERDICT_RETAIN,
    FastPathVerdict,
    consume_completed_adjudications,
    consume_verdict,
)
from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.policy import FastPathDecision
from core.response.fastpath.rollback import (
    RELEASE_REASON_ADJUDICATED,
    RELEASE_REASON_HUMAN,
    SOURCE_ADJUDICATOR,
    SOURCE_HUMAN,
    EscalationRequest,
    RollbackService,
)
from core.response.fastpath.speculative_service import SpeculativeActionService
from core.storage.models import ApprovalAction, WorkflowRun
from core.storage.unit_of_work import unit_of_work
from core.workflows.workflow_run_service import WorkflowRunService

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]

_no_counter = [0]


def _target(n: int) -> str:
    return f"203.0.113.{n}"


def _config(**overrides) -> FastPathConfig:
    defaults = {"enabled": True, "adjudication_enabled": True}
    defaults.update(overrides)
    return FastPathConfig(**defaults)


class _RecordingAdapter:
    simulates = False
    name = "recording"

    def __init__(self):
        self.applies: list = []
        self.releases: list = []

    def applies_to(self):
        return frozenset({"rate_limit", "tarpit", "session_pin", "latency_inject"})

    def apply(self, action):
        self.applies.append(action.action_id)
        return EnforceResult(True, "rs-1:rule-1", "enforced")

    def release(self, action):
        self.releases.append(action.action_id)
        return EnforceResult(True, None, "released")


def _services(config=None):
    adapter = _RecordingAdapter()
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
    return speculative, rollback, adapter, cfg


@pytest.fixture(autouse=True)
def _leave_no_live_speculative_rows():
    yield
    with unit_of_work() as session:
        session.query(ApprovalAction).filter(
            ApprovalAction.status == ActionStatus.SPECULATIVE.value
        ).update({ApprovalAction.status: ActionStatus.ROLLED_BACK.value})
        # The verdict scan is a global sweep over pending run rows — clear
        # any this test (or an earlier failure) left behind, so the next
        # scan test sees only its own queue.
        pending = (
            session.query(WorkflowRun)
            .filter(
                WorkflowRun.trigger_context["verdict_status"].astext
                == VERDICT_PENDING
            )
            .all()
        )
        for run in pending:
            run.trigger_context = dict(run.trigger_context, verdict_status="consumed")


def _make_speculative(config=None):
    """One live speculative row, with its services and adapter."""
    _no_counter[0] += 1
    speculative, rollback, adapter, cfg = _services(config=config)
    decision = FastPathDecision(
        action_type="rate_limit",
        target=_target(60 + _no_counter[0]),
        ttl_seconds=600,
        rule="fast_path.review_threshold=0.85 met (0.92)",
        signals={
            "tier": "t1",
            "finding_id": f"f-{_no_counter[0]}",
            "severity": "critical",
            "confidence": 0.92,
        },
    )
    outcome = speculative.create_speculative_action(decision)
    assert outcome is not None and outcome.inserted
    return outcome.action, rollback, adapter, cfg


def _adjudication_run(action_id: str) -> str:
    """A pending adjudication run row for one speculative action."""
    runs = WorkflowRunService()
    run_id = runs.begin_run(
        workflow_id="shadow-adjudication",
        workflow_name="shadow-adjudication",
        workflow_source="agent",
        trigger_context={
            "run_kind": "adjudicate",
            "speculative_action_id": action_id,
            "verdict_status": VERDICT_PENDING,
        },
        triggered_by="fast-path",
    )
    assert run_id is not None
    return run_id


def _completed_run(action_id: str) -> str:
    run_id = _adjudication_run(action_id)
    assert WorkflowRunService().finalize_run(run_id, status="completed")
    return run_id


def _run_row(run_id: str) -> WorkflowRun:
    with unit_of_work() as session:
        row = session.get(WorkflowRun, run_id)
        assert row is not None
        session.expunge(row)
        return row


def _live_row(action_id: str) -> ApprovalAction:
    with unit_of_work() as session:
        row = session.get(ApprovalAction, action_id)
        assert row is not None
        session.expunge(row)
        return row


def _full_actions() -> List[ApprovalAction]:
    with unit_of_work() as session:
        rows = (
            session.query(ApprovalAction)
            .filter(ApprovalAction.action_type.in_(["waf_block", "isolate_host"]))
            .all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def _conclude_events(verdict: str, **extra) -> List[Dict[str, Any]]:
    decision: Dict[str, Any] = {
        "action": "CONCLUDE",
        "verdict": verdict,
        "rationale": extra.pop("rationale", "the benign account stood"),
        "stated_confidence": 0.86,
    }
    decision.update(extra)
    return [{"kind": "decision", "payload": {"decision": decision}}]


def _reader_returning(events: Optional[List[Dict[str, Any]]]):
    async def read(run_id: str) -> Optional[List[Dict[str, Any]]]:
        return events

    return read


def _run_scan(config, rollback, reader) -> Dict[str, int]:
    return asyncio.run(
        consume_completed_adjudications(
            config=config, rollback=rollback, events_reader=reader
        )
    )


class TestReleaseVerdict:
    def test_release_marks_the_row_rolled_back(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _completed_run(action.action_id)

        outcome = consume_verdict(
            action.action_id,
            FastPathVerdict(verdict=VERDICT_RELEASE, rationale="benign"),
            run_id=run_id,
            config=config,
            rollback=rollback,
        )

        assert outcome.applied
        row = _live_row(action.action_id)
        assert row.status == ActionStatus.ROLLED_BACK.value
        assert row.execution_result["reason"] == RELEASE_REASON_ADJUDICATED
        assert row.execution_result["actor"] == f"adjudicator:{run_id}"
        assert adapter.releases == [action.action_id]
        run = _run_row(run_id)
        assert run.trigger_context["verdict_status"] == "consumed"


class TestEscalateVerdict:
    def test_escalate_creates_the_full_action_through_the_approval_pipeline(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _completed_run(action.action_id)
        before = len(_full_actions())

        outcome = consume_verdict(
            action.action_id,
            FastPathVerdict(
                verdict=VERDICT_ESCALATE,
                rationale="credential stuffing confirmed",
                proposed_full_action={"action_type": "waf_block"},
            ),
            run_id=run_id,
            config=config,
            rollback=rollback,
        )

        assert outcome.applied
        row = _live_row(action.action_id)
        assert row.status == ActionStatus.ESCALATED.value
        # The full action went through the unmodified pipeline: a pending
        # human-gated row — not an executed block.
        full = _full_actions()
        assert len(full) == before + 1
        newest = max(
            (a for a in full if a.action_id != action.action_id),
            key=lambda a: a.created_at,
        )
        assert newest.action_type == "waf_block"
        assert newest.requires_approval is True
        assert newest.status == ActionStatus.PENDING.value
        # The speculative row names who escalated and what it became.
        assert row.parameters["escalation"]["source"] == SOURCE_ADJUDICATOR
        assert newest.action_id in row.parameters["escalation"]["action_id"]
        # No enforcement beyond the fast path's own dispatch: the full
        # action waits for a person.
        assert adapter.applies == [action.action_id]
        run = _run_row(run_id)
        assert run.trigger_context["verdict_status"] == "consumed"

    def test_an_escalation_without_a_proposed_action_is_refused(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _completed_run(action.action_id)
        before = len(_full_actions())

        outcome = consume_verdict(
            action.action_id,
            FastPathVerdict(verdict=VERDICT_ESCALATE, rationale="escalate, trust me"),
            run_id=run_id,
            config=config,
            rollback=rollback,
        )

        assert not outcome.applied
        assert not outcome.superseded
        assert _live_row(action.action_id).status == ActionStatus.SPECULATIVE.value
        assert len(_full_actions()) == before
        run = _run_row(run_id)
        assert run.trigger_context["verdict_status"] == "refused"


class TestRetainVerdict:
    def test_retain_extends_expiry_once_and_clamps(self):
        action, rollback, adapter, config = _make_speculative(
            config=_config(max_ttl_seconds=900)
        )
        run_id = _completed_run(action.action_id)
        original_expiry = _live_row(action.action_id).expires_at

        outcome = consume_verdict(
            action.action_id,
            FastPathVerdict(
                verdict=VERDICT_RETAIN, rationale="unresolved", retention_seconds=7200
            ),
            run_id=run_id,
            config=config,
            rollback=rollback,
        )

        assert outcome.applied
        row = _live_row(action.action_id)
        assert row.status == ActionStatus.SPECULATIVE.value
        # Clamped to the ceiling — extended, but never past max_ttl_seconds.
        assert row.expires_at is not None
        assert original_expiry is not None
        assert row.expires_at > original_expiry
        assert row.parameters["adjudication"]["retention"] is not None

    def test_a_second_retain_verdict_does_not_extend_again(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _completed_run(action.action_id)
        first = consume_verdict(
            action.action_id,
            FastPathVerdict(verdict=VERDICT_RETAIN, retention_seconds=300),
            run_id=run_id,
            config=config,
            rollback=rollback,
        )
        assert first.applied
        expiry_after_first = _live_row(action.action_id).expires_at

        second = consume_verdict(
            action.action_id,
            FastPathVerdict(verdict=VERDICT_RETAIN, retention_seconds=300),
            run_id=run_id,
            config=config,
            rollback=rollback,
        )

        assert not second.applied
        assert _live_row(action.action_id).expires_at == expiry_after_first
        run = _run_row(run_id)
        assert run.trigger_context["verdict_status"] == "refused"


class TestSupersession:
    def test_a_human_release_wins_over_a_late_verdict(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _completed_run(action.action_id)
        rollback.release(action.action_id, RELEASE_REASON_HUMAN, "analyst@example.com")
        human_reason = _live_row(action.action_id).execution_result["reason"]

        outcome = consume_verdict(
            action.action_id,
            FastPathVerdict(verdict=VERDICT_ESCALATE, rationale="too late"),
            run_id=run_id,
            config=config,
            rollback=rollback,
        )

        assert not outcome.applied
        assert outcome.superseded
        # The human's resolution stands untouched.
        row = _live_row(action.action_id)
        assert row.status == ActionStatus.ROLLED_BACK.value
        assert row.execution_result["reason"] == human_reason
        assert adapter.applies == [action.action_id]
        # The disagreement is on the run row, with the resolver named.
        run = _run_row(run_id)
        assert run.trigger_context["verdict_status"] == "superseded"
        assert "human_release" in run.trigger_context["resolved_by"]

    def test_a_human_escalation_wins_and_no_second_action_is_created(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _completed_run(action.action_id)
        rollback.escalate(
            action.action_id,
            EscalationRequest(
                action_type="waf_block",
                target=action.target,
                confidence=0.9,
                reasoning="human call",
            ),
            decided_by="analyst@example.com",
            source=SOURCE_HUMAN,
        )
        before = len(_full_actions())

        outcome = consume_verdict(
            action.action_id,
            FastPathVerdict(
                verdict=VERDICT_RELEASE, rationale="the adjudicator disagrees"
            ),
            run_id=run_id,
            config=config,
            rollback=rollback,
        )

        assert not outcome.applied
        assert outcome.superseded
        assert len(_full_actions()) == before
        assert adapter.releases == []
        run = _run_row(run_id)
        assert run.trigger_context["verdict_status"] == "superseded"

    def test_a_late_verdict_after_the_ttl_sweep_changes_nothing(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _completed_run(action.action_id)
        with unit_of_work() as session:
            row = session.get(ApprovalAction, action.action_id)
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        assert rollback.expire().released == 1

        outcome = consume_verdict(
            action.action_id,
            FastPathVerdict(
                verdict=VERDICT_RETAIN, rationale="wait", retention_seconds=300
            ),
            run_id=run_id,
            config=config,
            rollback=rollback,
        )

        assert not outcome.applied
        assert outcome.superseded
        row = _live_row(action.action_id)
        assert row.status == ActionStatus.ROLLED_BACK.value
        run = _run_row(run_id)
        assert run.trigger_context["verdict_status"] == "superseded"
        assert "ttl_expired" in run.trigger_context["resolved_by"]


class TestConsumeCompletedAdjudications:
    def test_a_completed_run_with_a_verdict_is_consumed_once(self):
        action, rollback, adapter, config = _make_speculative()
        _completed_run(action.action_id)

        counts = _run_scan(
            config, rollback, _reader_returning(_conclude_events(VERDICT_RELEASE))
        )

        assert counts["examined"] == 1
        assert counts["consumed"] == 1
        assert _live_row(action.action_id).status == ActionStatus.ROLLED_BACK.value

        # The marker moved: a second scan examines nothing.
        again = _run_scan(
            config, rollback, _reader_returning(_conclude_events(VERDICT_RELEASE))
        )
        assert again["examined"] == 0

    def test_a_run_that_ended_without_a_verdict_is_refused_and_the_row_waits(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _completed_run(action.action_id)

        counts = _run_scan(
            config,
            rollback,
            _reader_returning(
                [{"kind": "decision", "payload": {"decision": {"action": "CONCLUDE"}}}]
            ),
        )

        assert counts["refused"] == 1
        assert _live_row(action.action_id).status == ActionStatus.SPECULATIVE.value
        assert _run_row(run_id).trigger_context["verdict_status"] == "refused"

    def test_a_non_completed_run_is_refused_without_reading_its_ledger(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _adjudication_run(action.action_id)
        assert WorkflowRunService().finalize_run(run_id, status="failed")

        async def must_not_read(rid: str):
            raise AssertionError("a failed run's ledger must not be read")

        counts = _run_scan(config, rollback, must_not_read)

        assert counts["refused"] == 1
        assert _live_row(action.action_id).status == ActionStatus.SPECULATIVE.value

    def test_an_unreachable_agent_layer_leaves_the_run_for_the_next_tick(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _completed_run(action.action_id)

        async def unreachable(rid: str):
            raise ConnectionError("agent layer down")

        counts = _run_scan(config, rollback, unreachable)

        assert counts["unavailable"] == 1
        assert counts["refused"] == 0
        # Still pending — retried next tick, not spent.
        assert _run_row(run_id).trigger_context["verdict_status"] == VERDICT_PENDING

        counts = _run_scan(
            config, rollback, _reader_returning(_conclude_events(VERDICT_RELEASE))
        )
        assert counts["consumed"] == 1
        assert _live_row(action.action_id).status == ActionStatus.ROLLED_BACK.value

    def test_a_missing_ledger_is_refused(self):
        action, rollback, adapter, config = _make_speculative()
        run_id = _completed_run(action.action_id)

        counts = _run_scan(config, rollback, _reader_returning(None))

        assert counts["refused"] == 1
        assert _live_row(action.action_id).status == ActionStatus.SPECULATIVE.value
        assert _run_row(run_id).trigger_context["verdict_status"] == "refused"
