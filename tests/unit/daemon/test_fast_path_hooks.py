"""The processor's fast-path hooks: inline dispatch at the two seams.

Pins the rollout slice's acceptance properties against the real processor
path and the real speculative service, with a stub enforcement adapter:

- A T1 pass at Gate 1 creates the speculative row and its
  ``execution_result`` within the evaluation call itself — no queue hop, no
  poller, no model call stands between the policy's yes and the adapter's
  apply (the row and the apply record exist the moment the await returns,
  and nothing else in the test process could have applied it).
- The default (disabled) config changes nothing: no rows, no service
  constructed, and the slow path queues and triggers exactly as before.
- The T0 slot exists after finding storage and is inert while gated; with
  the double opt-in it fires pre-triage and a later T1 pass dedupes
  against its live row instead of dispatching twice.
- A fast-path failure never fails the evaluation: the slow path's queue
  put and intake trigger land anyway, and the error is counted.

The throwaway database is session-scoped, so every test uses its own
target IP and never collides on the idempotency key the service derives
from type and target.
"""

import asyncio
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import func, select

from core.response.approval_service import ActionStatus, ApprovalService
from core.response.config import ResponseConfig
from core.response.fastpath.adapters import EnforcementRegistry, EnforceResult
from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.speculative_service import SpeculativeActionService
from core.storage.models import ApprovalAction, IntakeTrigger
from core.storage.unit_of_work import unit_of_work
from services.daemon.config import ProcessingConfig
from services.daemon.probes import PROBE_DATA_SOURCE
from services.daemon.processor import FindingProcessor

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]


class _RecordingAdapter:
    """Counts apply calls and records what it saw; never touches a network."""

    simulates = False
    name = "recording"

    def __init__(self):
        self.applies: List[str] = []

    def applies_to(self):
        return frozenset({"rate_limit", "tarpit", "session_pin", "latency_inject"})

    def apply(self, action):
        self.applies.append(action.action_id)
        return EnforceResult(True, "rs-1:rule-1", "enforced")

    def release(self, action):
        return EnforceResult(True, None, "released")


class _ExplodingService:
    """A speculative service that fails at the seam, every time."""

    def __init__(self, *args: Any, **kwargs: Any):
        pass

    def create_speculative_action(self, decision):
        raise RuntimeError("the ledger is unreachable")


class _Store:
    """Stand-in IngestionService: every store succeeds."""

    def __init__(self):
        self.stored: List[str] = []

    def ingest_finding(self, finding: Dict[str, Any]) -> bool:
        self.stored.append(finding["finding_id"])
        return True


def _target(n: int) -> str:
    return f"203.0.113.{n}"


def _finding(target: str, **overrides: Any) -> Dict[str, Any]:
    """A raw, pre-triage finding: severity is source-native, no triage fields."""
    finding: Dict[str, Any] = {
        "finding_id": f"f-{target}",
        "severity": "critical",
        "entity_context": {"src_ips": [target]},
        "data_source": "splunk",
    }
    finding.update(overrides)
    return finding


def _triaged_finding(target: str, **overrides: Any) -> Dict[str, Any]:
    """A finding carrying the triage stamps Gate 1 and the T1 tier read."""
    stamps: Dict[str, Any] = {
        "triage_confidence": 0.92,
        "recommended_action": "isolate",
    }
    stamps.update(overrides)
    return _finding(target, **stamps)


def _processor(
    target: int,
    fast_path_config: Optional[FastPathConfig] = None,
    service: Optional[Any] = None,
    adapter: Optional[_RecordingAdapter] = None,
) -> FindingProcessor:
    config = fast_path_config or FastPathConfig(enabled=True)
    processor = FindingProcessor(
        ProcessingConfig(auto_triage_enabled=False, auto_enrich_enabled=False),
        fast_path_config=config,
    )
    if service is not None:
        processor._fast_path_service = service
    elif config.enabled and adapter is not None:
        processor._fast_path_service = SpeculativeActionService(
            config=config,
            approvals=ApprovalService(config=ResponseConfig()),
            registry=EnforcementRegistry(
                {action_type: adapter for action_type in config.allowed_action_types}
            ),
        )
    return processor


def _speculative_rows(target: str) -> List[ApprovalAction]:
    """Live speculative rows for one target — the throwaway database is
    session-scoped, so counts must never span tests."""
    with unit_of_work() as session:
        rows = (
            session.execute(
                select(ApprovalAction).where(
                    ApprovalAction.status == ActionStatus.SPECULATIVE.value,
                    ApprovalAction.target == target,
                )
            )
            .scalars()
            .all()
        )
        session.expunge_all()
        return list(rows)


def _intake_trigger_count(finding_id: str) -> int:
    with unit_of_work() as session:
        return session.execute(
            select(func.count())
            .select_from(IntakeTrigger)
            .where(IntakeTrigger.finding_id == finding_id)
        ).scalar_one()


async def _drain_enrich_tasks(processor: FindingProcessor) -> None:
    """Let the processor's background enrich tasks finish their evaluation."""
    pending = list(processor._enrich_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


class TestT1AtGateOne:
    async def test_a_pass_creates_and_dispatches_the_row_inline(self):
        target = _target(1)
        adapter = _RecordingAdapter()
        processor = _processor(1, adapter=adapter)
        queue: asyncio.Queue = asyncio.Queue()
        processor.set_response_queue(queue)

        await processor._evaluate_for_response(_triaged_finding(target))

        # The dispatch happened inside the call: the adapter applied during
        # the evaluation, and the committed row already carries the outcome.
        assert len(adapter.applies) == 1
        rows = _speculative_rows(target)
        assert len(rows) == 1
        row = rows[0]
        assert row.action_type == "rate_limit"
        assert row.target == target
        assert row.status == ActionStatus.SPECULATIVE.value
        assert row.execution_result["applied"] is True
        assert row.execution_result["external_ref"] == "rs-1:rule-1"
        assert row.parameters["signals"]["tier"] == "t1"
        # The slow path is untouched and never gated: the response candidate
        # was queued and the intake trigger inserted by the same evaluation.
        candidate = queue.get_nowait()
        assert candidate["type"] == "response_candidate"
        assert processor.stats["queued_for_response"] == 1
        assert _intake_trigger_count(f"f-{target}") == 1
        assert processor.stats["fast_path_fired"] == 1
        assert processor.stats["fast_path_errors"] == 0

    async def test_a_finding_below_the_review_floor_is_never_restricted(self):
        target = _target(2)
        adapter = _RecordingAdapter()
        processor = _processor(2, adapter=adapter)
        queue: asyncio.Queue = asyncio.Queue()
        processor.set_response_queue(queue)

        below_floor = _triaged_finding(target, triage_confidence=0.60)
        await processor._evaluate_for_response(below_floor)

        # Gate 1 still responds on severity; the fast path fires no easier
        # than the review line, so no restriction appears.
        assert _speculative_rows(target) == []
        assert adapter.applies == []
        assert processor.stats["queued_for_response"] == 1
        assert _intake_trigger_count(f"f-{target}") == 1


class TestDisabledConfig:
    async def test_the_default_config_produces_no_rows_and_no_behavior_change(self):
        target = _target(3)
        # No service seeded: with the default config the processor must never
        # construct one, and the evaluation must behave exactly as before.
        processor = _processor(3, fast_path_config=FastPathConfig())
        queue: asyncio.Queue = asyncio.Queue()
        processor.set_response_queue(queue)

        await processor._evaluate_for_response(_triaged_finding(target))

        assert _speculative_rows(target) == []
        assert processor._fast_path_service is None
        assert processor.stats["fast_path_fired"] == 0
        assert processor.stats["fast_path_errors"] == 0
        # The slow path ran unchanged.
        assert processor.stats["queued_for_response"] == 1
        assert _intake_trigger_count(f"f-{target}") == 1


class TestT0PreTriage:
    async def test_a_double_optin_fires_pre_triage_before_any_model_call(
        self, monkeypatch
    ):
        target = _target(4)
        store = _Store()
        monkeypatch.setattr(
            "core.ingestion.ingestion_service.IngestionService", lambda: store
        )
        adapter = _RecordingAdapter()
        config = FastPathConfig(enabled=True, pre_triage_enabled=True)
        processor = _processor(4, fast_path_config=config, adapter=adapter)
        processor._data_service = object()
        queue: asyncio.Queue = asyncio.Queue()
        processor.set_response_queue(queue)

        # Source-native signal basis: critical source severity plus MITRE
        # predictions — the exact predicate the T0 tier reads.
        finding = _finding(target, mitre_predictions={"T1110": 0.9})
        await processor._process_finding(finding)

        # The row exists the moment _process_finding returns — before any
        # triage or enrichment could have run — and it is a T0 decision.
        rows = _speculative_rows(target)
        assert len(rows) == 1
        assert rows[0].target == target
        assert rows[0].parameters["signals"]["tier"] == "t0"
        assert len(adapter.applies) == 1

        # Triage lands while the background evaluation is still pending, as
        # it does in production: the T1 pass then clears Gate 1 and reaches
        # the service, which dedupes against the live T0 row instead of
        # stacking a second restriction — still one dispatch, one row.
        finding.update(triage_confidence=0.92, recommended_action="isolate")
        await _drain_enrich_tasks(processor)
        assert len(_speculative_rows(target)) == 1
        assert adapter.applies == [rows[0].action_id]

    async def test_the_t0_slot_is_inert_while_gated(self, monkeypatch):
        target = _target(5)
        store = _Store()
        monkeypatch.setattr(
            "core.ingestion.ingestion_service.IngestionService", lambda: store
        )
        adapter = _RecordingAdapter()
        # The master switch is on but the pre-triage tier is off — its default.
        config = FastPathConfig(enabled=True)
        processor = _processor(5, fast_path_config=config, adapter=adapter)
        processor._data_service = object()
        queue: asyncio.Queue = asyncio.Queue()
        processor.set_response_queue(queue)

        # The same signal basis the T0 tier would act on — only the tier
        # gate differs from the double-optin test above.
        await processor._process_finding(
            _finding(target, mitre_predictions={"T1110": 0.9})
        )
        await _drain_enrich_tasks(processor)
        # The slot is present but inert while gated: no restriction from the
        # pre-triage pass, and the still-untriaged T1 pass refuses on the 0.5
        # default confidence. The slow path still ran.
        assert _speculative_rows(target) == []
        assert adapter.applies == []
        assert processor.stats["queued_for_response"] == 1
        assert _intake_trigger_count(f"f-{target}") == 1

    async def test_a_probe_is_never_restricted(self, monkeypatch):
        target = _target(6)
        store = _Store()
        monkeypatch.setattr(
            "core.ingestion.ingestion_service.IngestionService", lambda: store
        )
        config = FastPathConfig(enabled=True, pre_triage_enabled=True)
        processor = _processor(6, fast_path_config=config)
        processor._data_service = object()
        queue: asyncio.Queue = asyncio.Queue()
        processor.set_response_queue(queue)

        probe = _finding(target, data_source=PROBE_DATA_SOURCE)
        await processor._process_finding(probe)
        await _drain_enrich_tasks(processor)

        # No restriction from either tier. The probe still walks the slow
        # path — the known-answer exemption is fast-path-only.
        assert _speculative_rows(target) == []


class TestFailureIsolation:
    async def test_a_fast_path_failure_never_fails_the_evaluation(self, monkeypatch):
        target = _target(7)
        processor = _processor(
            7,
            fast_path_config=FastPathConfig(enabled=True),
            service=_ExplodingService(),
        )
        queue: asyncio.Queue = asyncio.Queue()
        processor.set_response_queue(queue)

        # Must not raise, whatever the fast path did internally.
        await processor._evaluate_for_response(_triaged_finding(target))

        # The slow path's queue put and intake trigger landed anyway.
        assert queue.qsize() == 1
        assert _intake_trigger_count(f"f-{target}") == 1
        assert _speculative_rows(target) == []
        assert processor.stats["fast_path_errors"] == 1
