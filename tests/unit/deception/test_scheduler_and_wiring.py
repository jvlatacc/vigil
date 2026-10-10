"""AC6/AC7 wiring — the sweep is registered, and the daemon carries the flag.

- The scheduler always registers the lease sweep (a posture disabled while
  leases are live must still see them released), with a bounded cadence.
- The processor's deception arm queues below the review threshold only for
  corroborated recon, and the default install queues nothing new.
- The responder's stats carry the honey counters the metrics endpoint reads.
"""

import asyncio
from collections import defaultdict

import pytest

from tests.unit.deception.fixtures import FakeProbeSignals, recon_finding

from core.deception.config import DeceptionConfig
from core.response.config import MtdConfig, ResponseConfig
from services.daemon.config import SchedulerConfig
from services.daemon.scheduler import TaskScheduler, _deception_sweep_interval
from services.daemon.processor import FindingProcessor

pytestmark = pytest.mark.unit


class TestSweepRegistration:
    def test_the_sweep_is_always_registered(self):
        scheduler = TaskScheduler(SchedulerConfig())
        names = [t.name for t in scheduler._tasks]
        assert "deception_lease_sweep" in names

    def test_the_sweep_does_not_run_on_start(self):
        scheduler = TaskScheduler(SchedulerConfig())
        task = next(t for t in scheduler._tasks if t.name == "deception_lease_sweep")
        assert task.run_on_start is False
        assert task.enabled is True
        assert asyncio.iscoroutinefunction(task.func)

    @pytest.mark.parametrize(
        ("ttl", "expected"),
        [(1, 60), (600, 60), (3600, 300), (86400, 300)],
    )
    def test_the_cadence_is_bounded(self, ttl, expected, monkeypatch):
        monkeypatch.setattr(
            DeceptionConfig,
            "from_settings",
            classmethod(lambda cls, s=None: DeceptionConfig(ttl_seconds=ttl)),
        )
        assert _deception_sweep_interval() == expected


def _processor(response_config, service=None, queue=None):
    """A processor with the fields _evaluate_for_response reads, and no more."""
    processor = FindingProcessor.__new__(FindingProcessor)
    processor.response_config = response_config
    processor._deception_signal_service = service
    # Main's bands beside the deception arm, both shipped-disabled: the MTD
    # candidate band and the Fast-Path gate (None reads the disabled default).
    processor.mtd_config = MtdConfig()
    processor.fastpath_config = None
    processor._response_queue = queue if queue is not None else asyncio.Queue()
    processor.stats = defaultdict(int)
    return processor


class TestTheProcessorArm:
    def test_the_default_install_queues_exactly_what_it_used_to(self):
        """Posture off (the shipped default): a low-confidence recon finding
        stays unqueued — the pre-feature behaviour, byte for byte."""
        queue = asyncio.Queue()
        processor = _processor(ResponseConfig(), queue=queue)
        asyncio.run(processor._evaluate_for_response(recon_finding()))
        assert queue.empty()
        assert processor.stats["queued_for_response"] == 0

    def test_a_high_severity_finding_queues_as_before(self, monkeypatch):
        # _evaluate_for_response also opens an investigation trigger for
        # should_respond findings — a DB write this unit test must not hit.
        # The import is function-local, so the patch target is the source.
        monkeypatch.setattr(
            "services.daemon.orchestrator.insert_intake_trigger", lambda **_: "trigger-1"
        )
        queue = asyncio.Queue()
        processor = _processor(ResponseConfig(), queue=queue)
        finding = recon_finding(severity="critical")
        asyncio.run(processor._evaluate_for_response(finding))
        assert queue.qsize() == 1
        item = queue.get_nowait()
        assert item["type"] == "response_candidate"
        assert item["deception_signal"] is False  # posture off

    def test_a_corroborated_recon_source_queues_below_the_review_threshold(self):
        from core.deception.config import DeceptionConfig

        service = FakeProbeSignals(DeceptionConfig(enabled=True), corroborated=True)
        queue = asyncio.Queue()
        processor = _processor(ResponseConfig(), service=service, queue=queue)
        finding = recon_finding(triage_confidence=0.3)  # far below review
        asyncio.run(processor._evaluate_for_response(finding))
        assert queue.qsize() == 1
        item = queue.get_nowait()
        assert item["deception_signal"] is True
        assert len(service.recorded) == 1  # the probe was logged

    def test_an_uncorroborated_recon_source_does_not_queue(self):
        from core.deception.config import DeceptionConfig

        service = FakeProbeSignals(DeceptionConfig(enabled=True), corroborated=False)
        queue = asyncio.Queue()
        processor = _processor(ResponseConfig(), service=service, queue=queue)
        finding = recon_finding(triage_confidence=0.3)
        asyncio.run(processor._evaluate_for_response(finding))
        assert queue.empty()

    def test_a_kill_switched_posture_does_not_queue(self):
        from core.deception.config import DeceptionConfig

        service = FakeProbeSignals(DeceptionConfig(enabled=True), kill_switch=True)
        queue = asyncio.Queue()
        processor = _processor(ResponseConfig(), service=service, queue=queue)
        finding = recon_finding()
        asyncio.run(processor._evaluate_for_response(finding))
        assert queue.empty()

    def test_a_predicate_failure_never_breaks_the_response_gate(self):
        class _Broken:
            config = DeceptionConfig(enabled=True)

            def __getattr__(self, name):
                raise RuntimeError("registry down")

        queue = asyncio.Queue()
        processor = _processor(ResponseConfig(), service=_Broken(), queue=queue)
        finding = recon_finding()  # not high severity — queued only via deception
        asyncio.run(processor._evaluate_for_response(finding))
        assert queue.empty()  # the deception arm answered False, nothing raised


class TestResponderStats:
    def test_the_honey_counters_exist_for_the_metrics_endpoint(self):
        from unittest.mock import MagicMock

        from services.daemon.config import EscalationConfig
        from services.daemon.responder import AutonomousResponder

        responder = AutonomousResponder(
            ResponseConfig(),
            EscalationConfig(),
            response_service=MagicMock(),
            approvals=MagicMock(),
        )
        for counter in (
            "honey_routed",
            "honey_reused",
            "honey_pending",
            "honey_released",
            "honey_failed",
        ):
            assert counter in responder.stats
            assert responder.stats[counter] == 0
