"""The merged CEP observability surface (spec AC 8).

The daemon-side contract under test: the MetricsServer's /status "cep"
section merges every component's stats — the tap's events/drops, the
engine's machine and seen-id counts, the graph's size and cap counters,
the snapshot manager's writes/failures/restores and the snapshot's age,
the pipeline's completed matches, and the bridge's proposed actions —
and /health shows CEP degradation as its own visible state without ever
going unhealthy from it (the spine and its acks are untouched), while a
dead CEP component task is still a failure like any other.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Tuple

from core.cep.bridge import CepResponseBridge
from core.cep.engine import CepEngine
from core.cep.graph import EntityGraph
from core.cep.pipeline import CepPipeline, EngineSnapshotState
from core.cep.rules import load_rules
from core.cep.snapshot import SnapshotManager
from core.cep.tap import CepTap
from services.daemon.metrics import MetricsConfig, MetricsServer

RULES_DIR = Path(__file__).resolve().parents[3] / "data" / "cep_rules"

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)

# The spine, as the daemon health tests wire it: stub components with
# real long-lived tasks, so /health reflects exactly the CEP delta.
_SPINE = ("poller", "kafka", "processor", "responder", "scheduler", "orchestrator")


def _ts(offset_s: int) -> str:
    return (T0 + timedelta(seconds=offset_s)).isoformat()


def _finding(finding_id: str, data_source: str, host: str, ts: str) -> Dict[str, Any]:
    return {
        "finding_id": finding_id,
        "data_source": data_source,
        "severity": "high",
        "timestamp": ts,
        "entity_context": {"hostnames": [host]},
        "mitre_predictions": {"T1486": 0.9},
    }


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


class _FakeStore:
    def __init__(self) -> None:
        self.fail_with: Any = None

    def save(self, payload: dict) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    def latest(self):
        return None

    def prune(self, retention_s: int) -> int:
        return 0


class _StubApprovals:
    """The gate as a stub: the bridge's counter must count proposals, not
    outcomes, so the row's shape is irrelevant here."""

    def create_action(self, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(action_id="action-1", status="pending")


async def _forever() -> None:
    await asyncio.Event().wait()


def _wired(
    degrade_tap: bool = False, fail_snapshots: bool = False
) -> Tuple[MetricsServer, Dict[str, Any]]:
    """The full CEP loop as the daemon's _init_components wires it, with
    one two-source sequence driven through and one snapshot written."""
    rules = load_rules(RULES_DIR)
    engine = CepEngine(rules)
    graph = EntityGraph()
    tap = CepTap(queue_max=10)
    tap.stats["cep_events_seen"] = 5
    tap.stats["cep_dropped_total"] = 2
    bridge = CepResponseBridge(_StubApprovals())
    pipeline = CepPipeline(
        engine=engine,
        rules=rules,
        graph=graph,
        bridge=bridge,
        tap_queue=tap.queue,
    )
    state = EngineSnapshotState(engine)
    store = _FakeStore()
    manager = SnapshotManager(
        graph=graph,
        store=store,
        interval_s=60,
        machines=state.machines_section(),
        seen_ids=state.seen_ids_section(),
    )

    if fail_snapshots:
        store.fail_with = RuntimeError("db down")
        assert manager.snapshot_once() is False
        store.fail_with = None
    else:
        assert manager.snapshot_once() is True

    host = "cep-metrics-host"
    pipeline.process_item(_item(_finding("m-1", "crowdstrike", host, _ts(10))))
    pipeline.process_item(_item(_finding("m-2", "splunk", host, _ts(50))))

    if degrade_tap:
        tap.stats["cep_degraded"] = 1

    server = MetricsServer(MetricsConfig())
    server.cep = tap
    server.cep_engine = engine
    server.cep_graph = graph
    server.cep_snapshots = manager
    server.cep_pipeline = pipeline
    server.cep_bridge = bridge
    return server, {
        "tap": tap,
        "engine": engine,
        "graph": graph,
        "manager": manager,
        "pipeline": pipeline,
        "bridge": bridge,
    }


async def _wire_spine(server: MetricsServer) -> None:
    server.poller = SimpleNamespace()
    server.kafka_ingestor = SimpleNamespace()
    server.processor = SimpleNamespace()
    server.responder = SimpleNamespace()
    server.scheduler = SimpleNamespace()
    server.orchestrator = SimpleNamespace(enabled=False)
    for name in _SPINE:
        server.register_task(name, asyncio.create_task(_forever()))


async def _wire_live_cep_tasks(server: MetricsServer) -> None:
    server.register_task("cep-engine", asyncio.create_task(_forever()))
    server.register_task("cep-snapshot", asyncio.create_task(_forever()))


async def _cleanup(server: MetricsServer) -> None:
    for task in server._tasks.values():
        task.cancel()
    await asyncio.gather(*server._tasks.values(), return_exceptions=True)


async def _health(server: MetricsServer) -> Tuple[int, Dict[str, Any]]:
    resp = await server._handle_health(None)
    return resp.status, json.loads(resp.body)


def test_status_cep_section_merges_every_component() -> None:
    server, _refs = _wired()

    cep = server._collect_metrics()["cep"]

    # The tap's own counters (shipped in #41)...
    assert cep["cep_events_seen"] == 5
    assert cep["cep_dropped_total"] == 2
    assert cep["cep_degraded"] == 0
    # ...the engine's counts and the graph's size and cap counters...
    assert "cep_machines" in cep
    assert "cep_seen_ids" in cep
    assert cep["cep_graph_nodes"] >= 3  # two findings and their host
    assert cep["cep_graph_edges"] >= 2
    assert "cep_graph_nodes_evicted" in cep
    assert "cep_graph_edges_rejected" in cep
    # ...the snapshot story — one write, zero failures, no restore, and a
    # fresh age...
    assert cep["cep_snapshots_written"] == 1
    assert cep["cep_snapshot_failures"] == 0
    assert cep["cep_snapshot_restored"] == 0
    assert cep["cep_snapshot_degraded"] == 0
    assert 0.0 <= cep["cep_snapshot_age_seconds"] < 5.0
    # ...and the two counters this PR adds to the event sites.
    assert cep["cep_matches_total"] == 1
    assert cep["cep_actions_proposed"] == 1


def test_snapshot_age_absent_before_any_snapshot() -> None:
    server, refs = _wired()
    refs["manager"].last_snapshot_at = None

    cep = server._collect_metrics()["cep"]

    assert "cep_snapshot_age_seconds" not in cep


def test_status_without_cep_has_no_section() -> None:
    server = MetricsServer(MetricsConfig())

    assert "cep" not in server._collect_metrics()


async def test_health_shows_a_healthy_cep_loop() -> None:
    server, _refs = _wired()
    await _wire_spine(server)
    await _wire_live_cep_tasks(server)
    try:
        status, health = await _health(server)
    finally:
        await _cleanup(server)

    assert status == 200
    assert health["status"] == "healthy"
    assert health["components"]["cep"] == "running"
    assert health["components"]["cep-engine"] == "running"
    assert health["components"]["cep-snapshot"] == "running"


async def test_tap_overflow_is_degraded_but_never_unhealthy() -> None:
    server, _refs = _wired(degrade_tap=True)
    await _wire_spine(server)
    await _wire_live_cep_tasks(server)
    try:
        status, health = await _health(server)
    finally:
        await _cleanup(server)

    assert status == 200
    assert health["status"] == "healthy"
    assert health["components"]["cep"] == "degraded"


async def test_snapshot_failure_is_degraded_but_never_unhealthy() -> None:
    server, _refs = _wired(fail_snapshots=True)
    await _wire_spine(server)
    await _wire_live_cep_tasks(server)
    try:
        status, health = await _health(server)
    finally:
        await _cleanup(server)

    assert status == 200
    assert health["status"] == "healthy"
    assert health["components"]["cep"] == "degraded"


async def test_disabled_cep_is_a_deliberate_absence() -> None:
    server = MetricsServer(MetricsConfig())
    await _wire_spine(server)
    try:
        status, health = await _health(server)
    finally:
        await _cleanup(server)

    assert status == 200
    assert health["status"] == "healthy"
    assert health["components"]["cep"] == "disabled"
    assert health["components"]["cep-engine"] == "disabled"
    assert health["components"]["cep-snapshot"] == "disabled"


async def test_dead_cep_engine_task_is_still_a_failure() -> None:
    """The contrast pin: degradation is visible-but-healthy, a dead task
    is a dead component — the probes restart the daemon for it."""
    server, _refs = _wired()
    await _wire_spine(server)
    await _wire_live_cep_tasks(server)

    async def boom() -> None:
        raise RuntimeError("boom")

    dead = asyncio.create_task(boom())
    await asyncio.gather(dead, return_exceptions=True)
    server.register_task("cep-engine", dead)
    try:
        status, health = await _health(server)
    finally:
        await _cleanup(server)

    assert status == 503
    assert health["status"] == "unhealthy"
    assert health["components"]["cep-engine"].startswith("failed")
