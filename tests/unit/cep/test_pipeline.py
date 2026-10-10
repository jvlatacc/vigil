"""End-to-end tests for the CEP pipeline (tap queue -> engine -> bridge).

The shipped ransomware-staging-2src rule is the script: a CrowdStrike EDR
finding and a Splunk finding on one host, inside the rule's windows, must
produce exactly one ``create_action`` on the (stubbed) gate — with the
corroboration bonus, the linked graph path, and the full rendered
evidence. A sequence across different hosts fires nothing. The pipeline
tests also pin the isolation contract: a graph fault or a gate fault
costs only its own contribution; the loop keeps running.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest

from core.cep.bridge import CepResponseBridge
from core.cep.engine import CepEngine
from core.cep.graph import EntityGraph
from core.cep.pipeline import CepPipeline
from core.cep.rules import CepRule, load_rules
from core.cep.tap import CepTap, FindingTeeQueue
from core.response.approval_service import ActionType

RULES_DIR = Path(__file__).resolve().parents[3] / "data" / "cep_rules"

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


def _ts(offset_s: int) -> str:
    return (T0 + timedelta(seconds=offset_s)).isoformat()


def _item(data: Dict[str, Any]) -> Dict[str, Any]:
    """A daemon finding-queue item as the processor consumes it."""
    return {
        "type": "finding",
        "source": "test",
        "data": data,
        "timestamp": _ts(0),
        "dedup": None,
        "dedup_key": None,
    }


def _crowdstrike_finding(finding_id: str, host: str, ts: str) -> Dict[str, Any]:
    return {
        "finding_id": finding_id,
        "data_source": "crowdstrike",
        "severity": "high",
        "timestamp": ts,
        "entity_context": {"hostnames": [host]},
        "mitre_predictions": {"T1486": 0.9},
    }


def _splunk_finding(finding_id: str, host: str, ts: str) -> Dict[str, Any]:
    return {
        "finding_id": finding_id,
        "data_source": "splunk",
        "severity": "high",
        "timestamp": ts,
        "entity_context": {"hostnames": [host]},
        "mitre_predictions": {"T1486": 0.7, "T1070": 0.6},
    }


class _RecordingApprovals:
    """The gate as a record (see test_bridge.py)."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def create_action(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        # Attribute-shaped like the row object the real service hands back.
        return SimpleNamespace(action_id=f"action-{len(self.calls)}", status="pending")


def _pipeline(
    approvals: _RecordingApprovals,
    tap: CepTap,
    rules: Tuple[CepRule, ...] | None = None,
    graph: EntityGraph | None = None,
) -> Tuple[CepPipeline, EntityGraph]:
    """Build the loop over one shared graph — tests assert on that instance."""
    loaded = rules if rules is not None else load_rules(RULES_DIR)
    shared_graph = graph if graph is not None else EntityGraph()
    pipeline = CepPipeline(
        engine=CepEngine(loaded),
        rules=loaded,
        graph=shared_graph,
        bridge=CepResponseBridge(approvals),
        tap_queue=tap.queue,
    )
    return pipeline, shared_graph


async def _until(predicate: Any, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met before the timeout")
        await asyncio.sleep(0.01)


async def test_end_to_end_fires_isolate_host_through_the_gate() -> None:
    tap = CepTap(queue_max=10)
    tee = FindingTeeQueue(tap=tap, maxsize=10)
    approvals = _RecordingApprovals()
    pipeline, _shared_graph = _pipeline(approvals, tap)

    shutdown = asyncio.Event()
    task = asyncio.create_task(pipeline.run(shutdown))
    try:
        await tee.put(_item(_crowdstrike_finding("cs-1", "WKS-1", _ts(10))))
        await tee.put(_item(_splunk_finding("spl-1", "WKS-1", _ts(50))))
        await _until(lambda: approvals.calls)
    finally:
        shutdown.set()
        await asyncio.gather(task, return_exceptions=True)

    assert len(approvals.calls) == 1
    kwargs = approvals.calls[0]
    assert kwargs["action_type"] is ActionType.ISOLATE_HOST
    assert kwargs["target"] == "WKS-1"
    # base 0.82 + cross-source corroboration 0.10, straight off the engine
    assert kwargs["confidence"] == pytest.approx(0.92)
    assert kwargs["idempotency_key"].startswith(
        "cep:ransomware-staging-2src:host=WKS-1:"
    )

    params = kwargs["parameters"]
    assert params["source"] == "cep"
    assert params["finding_ids"] == ["cs-1", "spl-1"]
    assert params["data_sources"] == ["crowdstrike", "splunk"]
    # The opening finding links to its host through the entity graph.
    assert params["graph_path"] == ["finding:cs-1", "host:WKS-1"]
    evidence = kwargs["evidence"]
    assert "cep.rule=ransomware-staging-2src" in evidence
    assert "cep.finding[0]=cs-1" in evidence
    assert "cep.finding[1]=spl-1" in evidence
    assert "cep.graph_path=finding:cs-1 -> host:WKS-1" in evidence


async def test_cross_host_sequence_fires_nothing() -> None:
    tap = CepTap(queue_max=10)
    tee = FindingTeeQueue(tap=tap, maxsize=10)
    approvals = _RecordingApprovals()
    pipeline, _shared_graph = _pipeline(approvals, tap)

    shutdown = asyncio.Event()
    task = asyncio.create_task(pipeline.run(shutdown))
    try:
        await tee.put(_item(_crowdstrike_finding("cs-1", "WKS-1", _ts(10))))
        await tee.put(_item(_splunk_finding("spl-1", "WKS-2", _ts(50))))
        # Let the loop drain both items.
        await asyncio.sleep(0.05)
    finally:
        shutdown.set()
        await asyncio.gather(task, return_exceptions=True)

    assert approvals.calls == []


def test_pipeline_links_findings_and_entities_into_the_graph() -> None:
    tap = CepTap(queue_max=10)
    approvals = _RecordingApprovals()
    graph = EntityGraph()
    pipeline, shared_graph = _pipeline(approvals, tap, graph=graph)

    matches = pipeline.process_item(
        _item(_crowdstrike_finding("cs-1", "WKS-1", _ts(10)))
    )

    assert matches == []
    # One finding node + one host node, one observed_in edge.
    assert graph.node_count == 2
    assert graph.edge_count == 1
    assert graph.node_count == shared_graph.node_count


def test_pipeline_skips_items_that_are_not_findings() -> None:
    tap = CepTap(queue_max=10)
    approvals = _RecordingApprovals()
    graph = EntityGraph()
    pipeline, _shared_graph = _pipeline(approvals, tap, graph=graph)

    assert pipeline.process_item({"type": "shutdown"}) == []
    assert pipeline.process_item({"type": "finding", "data": "not-a-dict"}) == []
    assert pipeline.process_item("garbage") == []
    assert graph.node_count == 0
    assert approvals.calls == []


def test_graph_fault_costs_only_graph_evidence() -> None:
    tap = CepTap(queue_max=10)
    approvals = _RecordingApprovals()
    graph = EntityGraph()
    pipeline, shared_graph = _pipeline(approvals, tap, graph=graph)

    def exploding_link(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("graph down")

    shared_graph.link = exploding_link  # type: ignore[method-assign]

    first = pipeline.process_item(_item(_crowdstrike_finding("cs-1", "WKS-1", _ts(10))))
    second = pipeline.process_item(_item(_splunk_finding("spl-1", "WKS-1", _ts(50))))

    # The engine still completed the sequence and the gate still got its
    # proposal — only the graph path evidence is absent.
    assert first == [] and len(second) == 1
    assert len(approvals.calls) == 1
    assert approvals.calls[0]["parameters"]["graph_path"] is None


def test_gate_fault_is_contained_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    tap = CepTap(queue_max=10)
    graph = EntityGraph()

    class ExplodingApprovals:
        def create_action(self, **kwargs: Any) -> Any:
            raise RuntimeError("db down")

    rules = load_rules(RULES_DIR)
    pipeline = CepPipeline(
        engine=CepEngine(rules),
        rules=rules,
        graph=graph,
        bridge=CepResponseBridge(ExplodingApprovals()),
        tap_queue=tap.queue,
    )

    with caplog.at_level("ERROR"):
        pipeline.process_item(_item(_crowdstrike_finding("cs-1", "WKS-1", _ts(10))))
        matches = pipeline.process_item(
            _item(_splunk_finding("spl-1", "WKS-1", _ts(50)))
        )

    # The loop moved on: the match was produced (and logged), nothing raised.
    assert len(matches) == 1
    assert any("proposing" in record.message for record in caplog.records)
    assert list(matches[0].finding_ids) == ["cs-1", "spl-1"]


def test_match_stats_count_completed_sequences() -> None:
    """Spec AC 8: the pipeline's stats surface counts every completed
    sequence — the number MetricsServer mirrors into /status and OTEL."""
    tap = CepTap(queue_max=10)
    approvals = _RecordingApprovals()
    pipeline, _shared_graph = _pipeline(approvals, tap)
    assert pipeline.stats["cep_matches_total"] == 0

    assert (
        pipeline.process_item(_item(_crowdstrike_finding("cs-9", "WKS-9", _ts(10))))
        == []
    )
    matches = pipeline.process_item(_item(_splunk_finding("spl-9", "WKS-9", _ts(50))))

    assert len(matches) == 1
    assert pipeline.stats["cep_matches_total"] == 1
