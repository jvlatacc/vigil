"""Restart-replay integration test for the full CEP loop (spec AC 7).

Two "boots" of the same loop — tap-queue consumer, engine, entity graph,
bridge over a stubbed ApprovalService, SnapshotManager over a JSONB-like
fake store — sharing only what a real deployment would share: the
snapshot rows. Boot 1 snapshots a partially completed sequence; boot 2
restores it, replays the opening finding (swallowed by the restored
seen-ids), completes the sequence with the next finding, and exactly one
action reaches the gate. A second scenario proves a completed sequence
cannot re-fire across a restart: after restore, replaying both findings
produces no second proposal.

The fake store round-trips payloads through json.dumps/json.loads the way
Postgres JSONB would, so the boot-2 restore reads what production reads.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

from core.cep.bridge import CepResponseBridge
from core.cep.engine import CepEngine
from core.cep.graph import EntityGraph
from core.cep.pipeline import CepPipeline, EngineSnapshotState
from core.cep.rules import load_rules
from core.cep.snapshot import SnapshotManager

RULES_DIR = Path(__file__).resolve().parents[3] / "data" / "cep_rules"

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


class _RecordingApprovals:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def create_action(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        # Attribute-shaped like the row object the real service hands back.
        return SimpleNamespace(
            action_id=f"action-{len(self.calls)}", status="pending"
        )


class _FakeStore:
    """SnapshotStore stand-in: rows in memory, payloads JSONB-round-tripped."""

    def __init__(self) -> None:
        self.rows: List[Tuple[datetime, Dict[str, Any]]] = []

    def save(self, payload: Dict[str, Any]) -> None:
        self.rows.append((datetime.now(timezone.utc), _jsonb(payload)))

    def latest(self) -> Any:
        return self.rows[-1][1] if self.rows else None

    def prune(self, keep: int) -> None:
        # Retention is not under test here (see test_snapshot.py).
        _ = keep


def _jsonb(payload: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(payload))


def _finding(finding_id: str, source: str, host: str, offset_s: int) -> Dict[str, Any]:
    ts = (T0 + timedelta(seconds=offset_s)).isoformat()
    base: Dict[str, Any] = {
        "finding_id": finding_id,
        "data_source": source,
        "severity": "high",
        "timestamp": ts,
        "entity_context": {"hostnames": [host]},
    }
    if source == "crowdstrike":
        base["mitre_predictions"] = {"T1486": 0.9}
    else:
        base["mitre_predictions"] = {"T1486": 0.7, "T1070": 0.6}
    return base


def _item(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "finding",
        "source": "test",
        "data": data,
        "timestamp": data["timestamp"],
        "dedup": None,
        "dedup_key": None,
    }


def _boot(store: _FakeStore, approvals: _RecordingApprovals) -> Any:
    """One boot of the loop with its own engine, graph and pipeline."""
    rules = load_rules(RULES_DIR)
    engine = CepEngine(rules)
    graph = EntityGraph()
    state = EngineSnapshotState(engine)
    manager = SnapshotManager(
        graph=graph,
        store=store,
        interval_s=60,
        machines=state.machines_section(),
        seen_ids=state.seen_ids_section(),
    )
    pipeline = CepPipeline(
        engine=engine,
        rules=rules,
        graph=graph,
        bridge=CepResponseBridge(approvals),
        tap_queue=asyncio.Queue(),
    )
    return pipeline, manager, engine


async def test_partial_sequence_re_arms_after_restart() -> None:
    approvals = _RecordingApprovals()
    store = _FakeStore()

    # Boot 1: the EDR finding opens the sequence — no match yet.
    boot1_pipeline, boot1_manager, boot1_engine = _boot(store, approvals)
    boot1_pipeline.process_item(
        _item(_finding("cs-1", "crowdstrike", "WKS-1", 10))
    )
    assert approvals.calls == []

    boot1_manager.snapshot_once()
    payload = store.latest()
    assert payload["machines"], "the envelope must carry machine state"
    assert payload["seen_ids"], "the envelope must carry the seen ids"
    # machines is {rule_id: {entity_key: machine}} — descend both levels.
    rule_machines = next(iter(payload["machines"].values()))
    machine_state = next(iter(rule_machines.values()))
    assert machine_state["finding_ids"] == ["cs-1"]

    # Boot 2: restore, then replay the opening finding and complete the
    # sequence with the SIEM corroboration.
    boot2_pipeline, boot2_manager, boot2_engine = _boot(store, approvals)
    age_s = boot2_manager.restore()
    assert age_s is not None and age_s >= 0.0
    # The engine state came back exactly as boot 1 left it.
    assert boot2_engine.serialize_machines() == boot1_engine.serialize_machines()

    boot2_pipeline.process_item(
        _item(_finding("cs-1", "crowdstrike", "WKS-1", 10))
    )  # replay: swallowed by the restored seen-ids
    matches = boot2_pipeline.process_item(
        _item(_finding("spl-1", "splunk", "WKS-1", 50))
    )

    assert len(approvals.calls) == 1
    kwargs = approvals.calls[0]
    # The re-armed machine completed with BOTH findings — the replayed
    # opening contributes its restored id, the completing event its own.
    assert kwargs["parameters"]["finding_ids"] == ["cs-1", "spl-1"]
    assert kwargs["idempotency_key"].startswith(
        "cep:ransomware-staging-2src:host=WKS-1:"
    )
    assert len(matches) == 1


async def test_completed_sequence_does_not_refire_after_restart() -> None:
    approvals = _RecordingApprovals()
    store = _FakeStore()

    # Boot 1: the full sequence fires exactly once, then snapshots.
    boot1_pipeline, boot1_manager, _ = _boot(store, approvals)
    boot1_pipeline.process_item(
        _item(_finding("cs-1", "crowdstrike", "WKS-1", 10))
    )
    boot1_pipeline.process_item(
        _item(_finding("spl-1", "splunk", "WKS-1", 50))
    )
    assert len(approvals.calls) == 1

    boot1_manager.snapshot_once()

    # Boot 2: the same findings re-delivered (cursors only advance after
    # stored acks, so replay is bounded but real) — no duplicate action.
    boot2_pipeline, boot2_manager, _ = _boot(store, approvals)
    assert boot2_manager.restore() is not None
    boot2_pipeline.process_item(
        _item(_finding("cs-1", "crowdstrike", "WKS-1", 10))
    )
    boot2_pipeline.process_item(
        _item(_finding("spl-1", "splunk", "WKS-1", 50))
    )

    assert len(approvals.calls) == 1
