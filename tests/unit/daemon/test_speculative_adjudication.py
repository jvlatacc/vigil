"""The adjudication enqueue: the brief is built only after the row exists.

Pins the enqueue side of the dual-track integration against the throwaway
database and a recorded queue: the run is the shadow-adjudication mold
(same workflow id, run kind and enqueue mechanics), its brief carries the
committed speculative record — re-read from the ledger, never trusted
from memory — and the ordering guarantee is enforced, not assumed: a row
that does not exist, or is already resolved, enqueues nothing. A queue
refusal finalizes the run row failed and re-raises; the processor hook
keeps that failure away from the dispatch's own error count.
"""

from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import select

from core.response.approval_service import ActionStatus, ApprovalService, PendingAction
from core.response.config import ResponseConfig
from core.response.fastpath.adapters import EnforcementRegistry, EnforceResult
from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.policy import FastPathDecision
from core.response.fastpath.rollback import RollbackService
from core.response.fastpath.speculative_service import SpeculativeActionService
from core.storage.models import ApprovalAction, WorkflowRun
from core.storage.unit_of_work import unit_of_work
from services.daemon import speculative_adjudication as enqueue_module
from services.daemon.speculative_adjudication import (
    adjudication_run_id,
    enqueue_speculative_adjudication,
)

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]


class _RecordingAdapter:
    simulates = False
    name = "recording"

    def applies_to(self):
        return frozenset({"rate_limit"})

    def apply(self, action):
        return EnforceResult(True, "rs-1:rule-1", "enforced")

    def release(self, action):
        return EnforceResult(True, None, "released")


class _QueueRecorder:
    """Stands in for the BullMQ enqueue: records jobs, touches no Redis."""

    def __init__(self):
        self.jobs: List[Dict[str, Any]] = []
        self.refuse = False

    async def __call__(self, job: Dict[str, Any], job_id: Optional[str] = None):
        if self.refuse:
            raise RuntimeError("queue down")
        self.jobs.append(job)


@pytest.fixture(autouse=True)
def _recorded_queue(monkeypatch):
    recorder = _QueueRecorder()
    monkeypatch.setattr(enqueue_module, "enqueue_run", recorder)
    yield recorder


@pytest.fixture(autouse=True)
def _workflow_enabled(monkeypatch):
    monkeypatch.setattr(enqueue_module, "is_enabled", lambda workflow_id: True)


@pytest.fixture(autouse=True)
def _leave_no_live_speculative_rows():
    yield
    with unit_of_work() as session:
        session.query(ApprovalAction).filter(
            ApprovalAction.status == ActionStatus.SPECULATIVE.value
        ).update({ApprovalAction.status: ActionStatus.ROLLED_BACK.value})
        # The verdict scan sweeps every pending run row in the database —
        # spend the markers these tests leave, so a later scan test in the
        # same process sees only its own queue.
        pending = (
            session.query(WorkflowRun)
            .filter(
                WorkflowRun.trigger_context["verdict_status"].astext
                == "pending"
            )
            .all()
        )
        for run in pending:
            run.trigger_context = dict(run.trigger_context, verdict_status="consumed")


def _config(**overrides) -> FastPathConfig:
    defaults = {"enabled": True, "adjudication_enabled": True}
    defaults.update(overrides)
    return FastPathConfig(**defaults)


def _make_speculative(config: FastPathConfig):
    cfg = config
    adapter = _RecordingAdapter()
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
    decision = FastPathDecision(
        action_type="rate_limit",
        target="203.0.113.71",
        ttl_seconds=600,
        rule="fast_path.review_threshold=0.85 met (0.92)",
        signals={
            "tier": "t1",
            "finding_id": "f-enqueue-1",
            "severity": "critical",
            "confidence": 0.92,
        },
    )
    outcome = speculative.create_speculative_action(decision)
    assert outcome is not None and outcome.inserted
    return outcome.action, rollback


def _run_row(run_id: str) -> WorkflowRun:
    with unit_of_work() as session:
        row = session.get(WorkflowRun, run_id)
        assert row is not None
        session.expunge(row)
        return row


def _runs_for_action(action_id: str) -> List[WorkflowRun]:
    with unit_of_work() as session:
        rows = (
            session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.trigger_context["speculative_action_id"].astext
                    == action_id
                )
            )
            .scalars()
            .all()
        )
        session.expunge_all()
        return list(rows)


class TestEnqueue:
    async def test_the_brief_is_built_only_after_the_row_exists(
        self, _recorded_queue
    ):
        action, _ = _make_speculative(_config())

        run_id = await enqueue_speculative_adjudication(action, _config())

        assert run_id == adjudication_run_id(action.action_id)
        # The run row exists and names the row it adjudicates, pending.
        row = _run_row(run_id)
        assert row.trigger_context["run_kind"] == "adjudicate"
        assert row.trigger_context["speculative_action_id"] == action.action_id
        assert row.trigger_context["verdict_status"] == "pending"
        assert row.triggered_by == "fast-path"
        # The brief — the queue's job request — carries the committed
        # record: id, target, deciding rule, TTL, rollback recipe, signals.
        assert len(_recorded_queue.jobs) == 1
        job = _recorded_queue.jobs[0]
        assert job["run_kind"] == "adjudicate"
        assert job["enqueued_by"] == "fast-path"
        prompt = job["request"]["prompt"]
        assert action.action_id in prompt
        assert "203.0.113.71" in prompt
        assert "fast_path.review_threshold=0.85 met (0.92)" in prompt
        assert "600s" in prompt
        assert "rs-1:rule-1" in prompt
        assert "f-enqueue-1" in prompt
        # The verdict contract and the hypothesis it tests.
        assert '"release"' in prompt
        assert '"escalate"' in prompt
        assert '"retain"' in prompt
        assert job["request"]["hypotheses"]
        assert job["request"]["hypothesis_subjects"]
        # Orchestrator-default budgets ride the request, like any run.
        budgets = job["request"]["overrides"]["budgets"]
        assert budgets["max_calls"] > 0
        assert budgets["max_cost_usd"] > 0
        assert budgets["max_wall_ms"] > 0

    async def test_a_row_that_never_committed_enqueues_nothing(
        self, _recorded_queue
    ):
        never_stored = PendingAction(
            action_id="spec-never-stored",
            action_type="rate_limit",
            title="ghost",
            description="",
            target="203.0.113.72",
            confidence=0.92,
            reason="",
            evidence=[],
            created_at="2026-10-10T00:00:00Z",
            created_by="fast-path",
            requires_approval=False,
            status="speculative",
        )

        run_id = await enqueue_speculative_adjudication(never_stored, _config())

        assert run_id is None
        assert _recorded_queue.jobs == []

    async def test_an_already_resolved_row_enqueues_nothing(
        self, _recorded_queue
    ):
        action, rollback = _make_speculative(_config())
        rollback.release(action.action_id, "human_release", "analyst@example.com")

        run_id = await enqueue_speculative_adjudication(action, _config())

        assert run_id is None
        assert _recorded_queue.jobs == []

    async def test_the_config_switch_gates_the_enqueue(self, _recorded_queue):
        action, _ = _make_speculative(_config())

        run_id = await enqueue_speculative_adjudication(
            action, _config(adjudication_enabled=False)
        )

        assert run_id is None
        assert _recorded_queue.jobs == []

    async def test_a_disabled_workflow_enqueues_nothing(
        self, _recorded_queue, monkeypatch
    ):
        action, _ = _make_speculative(_config())
        monkeypatch.setattr(enqueue_module, "is_enabled", lambda workflow_id: False)

        run_id = await enqueue_speculative_adjudication(action, _config())

        assert run_id is None
        assert _recorded_queue.jobs == []

    async def test_a_repeated_enqueue_reuses_one_run(self, _recorded_queue):
        action, _ = _make_speculative(_config())

        first = await enqueue_speculative_adjudication(action, _config())
        again = await enqueue_speculative_adjudication(action, _config())

        assert first == again
        assert len(_recorded_queue.jobs) == 1
        assert _run_row(first).trigger_context["speculative_action_id"] == (
            action.action_id
        )

    async def test_a_queue_refusal_finalizes_the_run_failed_and_raises(
        self, _recorded_queue
    ):
        action, _ = _make_speculative(_config())
        _recorded_queue.refuse = True

        with pytest.raises(RuntimeError):
            await enqueue_speculative_adjudication(action, _config())

        row = _run_row(adjudication_run_id(action.action_id))
        assert row.status == "failed"
        assert "Could not enqueue" in (row.error or "")


class TestProcessorHook:
    async def test_an_enqueue_failure_is_not_a_dispatch_error(self, monkeypatch):
        from services.daemon.config import ProcessingConfig
        from services.daemon.processor import FindingProcessor

        action, _ = _make_speculative(_config())

        async def refusing(unused, config=None):
            raise RuntimeError("queue down")

        monkeypatch.setattr(
            enqueue_module, "enqueue_speculative_adjudication", refusing
        )
        processor = FindingProcessor(
            ProcessingConfig(auto_triage_enabled=False, auto_enrich_enabled=False),
            fast_path_config=_config(),
        )

        # The hook swallows: the dispatch already happened (the row is
        # live), and the enqueue failure is not a fast-path error.
        await processor._enqueue_adjudication(action)

        assert processor.stats["fast_path_errors"] == 0

    async def test_the_hook_gates_on_the_config_switch(self):
        from services.daemon.config import ProcessingConfig
        from services.daemon.processor import FindingProcessor

        action, _ = _make_speculative(_config())
        processor = FindingProcessor(
            ProcessingConfig(auto_triage_enabled=False, auto_enrich_enabled=False),
            fast_path_config=_config(adjudication_enabled=False),
        )

        await processor._enqueue_adjudication(action)

        # No run row was created for the action: the gate returned first.
        assert _runs_for_action(action.action_id) == []
