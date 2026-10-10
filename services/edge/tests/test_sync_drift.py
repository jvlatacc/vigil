"""The drift report: what was blocked and why, what reverted, what still
needs an analyst — classified from the partition's journal records."""

from __future__ import annotations

from services.edge.journal.journal import (
    KIND_DECISION,
    KIND_EXECUTE_FAILED,
    KIND_REVERT,
    KIND_STATE,
    JournalRecord,
)
from services.edge.sync.drift import build_drift_report

_SEQ = 0


def record(kind: str, payload: dict) -> JournalRecord:
    global _SEQ
    _SEQ += 1
    return JournalRecord(
        local_sequence=_SEQ,
        node_id="gw-test",
        boot_id="boot-1",
        timestamp=f"2026-10-09T12:00:{_SEQ:02d}+00:00",
        kind=kind,
        payload=payload,
        prev_hash="0" * 64,
        entry_hash="1" * 64,
    )


def decision(outcome: str, *, success: bool | None = None) -> JournalRecord:
    return record(
        KIND_DECISION,
        {
            "outcome": outcome,
            "rule_string": "edge.c2-egress-active tier=tier2 conf=0.95",
            "reason": "rule c2-egress-active",
            "actor": "edge:gw-test@v7",
            "confidence": 0.95,
            "bundle_version": 7,
            "model": {"id": "qwen2.5:1.5b", "digest": "sha256:abc"},
            "action": (
                {
                    "action_type": "block_ip",
                    "executor": "nftables",
                    "target": "203.0.113.55",
                    "ttl_seconds": 900,
                }
                if outcome == "execute"
                else None
            ),
            "execution": None if success is None else {"success": success, "ref": "r1"},
            "observation": {},
        },
    )


def test_executed_blocks_are_reported_with_model_version() -> None:
    report = build_drift_report(
        [decision("execute", success=True)],
        node_id="gw-test",
        boot_id="boot-1",
        opened_at="2026-10-09T11:00:00+00:00",
        closed_at="2026-10-09T12:00:00+00:00",
    )
    assert len(report.executed) == 1
    entry = report.executed[0]
    assert entry.target == "203.0.113.55"
    assert entry.action_type == "block_ip"
    assert entry.executor == "nftables"
    assert entry.model_id == "qwen2.5:1.5b"
    assert entry.model_digest == "sha256:abc"
    assert entry.confidence == 0.95
    assert not report.needs_analyst


def test_failed_applies_and_holds_need_analyst_not_executed() -> None:
    report = build_drift_report(
        [decision("execute", success=False), decision("hold")],
        node_id="gw-test",
        boot_id="boot-1",
        opened_at="2026-10-09T11:00:00+00:00",
        closed_at="2026-10-09T12:00:00+00:00",
    )
    assert report.executed == []
    assert len(report.pending_decision) == 2
    assert report.pending_decision[0].reason.startswith("apply_failed:")
    assert report.pending_decision[1].reason == "rule c2-egress-active"
    assert report.needs_analyst


def test_missing_executor_is_pending_not_executed() -> None:
    report = build_drift_report(
        [
            record(
                KIND_EXECUTE_FAILED,
                {
                    "reason": "no_executor_registered",
                    "executor": "nftables",
                    "action_type": "block_ip",
                    "target": "203.0.113.55",
                    "rule_string": "edge.c2-egress-active tier=tier2 conf=0.95",
                },
            )
        ],
        node_id="gw-test",
        boot_id="boot-1",
        opened_at="2026-10-09T11:00:00+00:00",
        closed_at="2026-10-09T12:00:00+00:00",
    )
    assert report.executed == []
    assert len(report.pending_decision) == 1
    assert report.pending_decision[0].reason == "no_executor:nftables"
    assert report.needs_analyst


def test_state_timeline_and_evidence_loss_flow_through() -> None:
    report = build_drift_report(
        [
            record(
                KIND_STATE,
                {"from": "synced", "to": "partitioned", "reason": "heartbeat: down"},
            ),
            record(
                KIND_STATE,
                {"from": "partitioned", "to": "reconciling", "reason": "link_restored"},
            ),
        ],
        node_id="gw-test",
        boot_id="boot-1",
        opened_at="2026-10-09T11:00:00+00:00",
        closed_at="2026-10-09T12:00:00+00:00",
        loss_counters={"observations_evicted": 3},
        evicted_ranges=[[10, 12]],
        rejected_events=[{"local_sequence": 9, "reason": "unknown_kind"}],
    )
    assert [t["to"] for t in report.state_timeline] == ["partitioned", "reconciling"]
    assert report.loss_counters == {"observations_evicted": 3}
    assert report.evicted_ranges == [[10, 12]]
    assert report.rejected_events[0]["reason"] == "unknown_kind"
    assert report.needs_analyst


def test_payload_round_trip_carries_the_whole_window() -> None:
    report = build_drift_report(
        [
            decision("execute", success=True),
            record(
                KIND_REVERT,
                {
                    "revert_of": 1,
                    "success": True,
                    "rule_string": "edge.x",
                    "reason": "ttl",
                    "action": {"target": "203.0.113.55"},
                },
            ),
        ],
        node_id="gw-test",
        boot_id="boot-1",
        opened_at="2026-10-09T11:00:00+00:00",
        closed_at="2026-10-09T12:00:00+00:00",
    )
    payload = report.to_payload()
    assert payload["phase"] == "close"
    assert payload["node_id"] == "gw-test"
    assert len(payload["executed"]) == 1
    assert len(payload["reverted"]) == 1
    assert payload["needs_analyst"] is False
    lines = report.to_lines()
    assert any("blocked:" in line for line in lines)
    assert any("reverted (TTL):" in line for line in lines)
