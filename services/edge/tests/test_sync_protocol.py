"""Journal record -> wire event mapping: executed decisions become action
events, everything else stays honest about what did and did not happen, and
local bookkeeping never uploads."""

from __future__ import annotations

import pytest

from services.edge.journal.journal import (
    KIND_DECISION,
    KIND_EXECUTE_FAILED,
    KIND_OBSERVATION,
    KIND_OFFLINE_WINDOW,
    KIND_REVERT,
    KIND_STATE,
    JournalRecord,
)
from services.edge.sync.protocol import (
    EventMappingError,
    batches,
    event_from_record,
    is_executed,
)

_SEQ = 0


def record(kind: str, payload: dict, *, seq: int | None = None) -> JournalRecord:
    global _SEQ
    _SEQ += 1
    sequence = seq if seq is not None else _SEQ
    return JournalRecord(
        local_sequence=sequence,
        node_id="gw-test",
        boot_id="boot-1",
        timestamp="2026-10-09T12:00:00+00:00",
        kind=kind,
        payload=payload,
        prev_hash="0" * 64,
        entry_hash="1" * 64,
    )


def decision_payload(outcome: str, *, success: bool | None = None) -> dict:
    payload = {
        "outcome": outcome,
        "rule_string": "edge.c2-egress-active tier=tier2 conf=0.95",
        "reason": "rule c2-egress-active",
        "actor": "edge:gw-test@v7",
        "confidence": 0.95,
        "bundle_version": 7,
        "model": {"id": "qwen2.5:1.5b", "digest": "sha256:abc"},
        "action": (
            None
            if outcome != "execute"
            else {
                "action_type": "block_ip",
                "executor": "nftables",
                "target": "203.0.113.55",
                "ttl_seconds": 900,
            }
        ),
        "execution": None if success is None else {"success": success, "ref": "r1"},
        "observation": {"raw_digest": "a" * 64},
    }
    return payload


def test_executed_decision_maps_to_action_event() -> None:
    event = event_from_record(
        record(KIND_DECISION, decision_payload("execute", success=True))
    )
    assert event is not None
    assert event["kind"] == "action"
    assert event["event_id"] == "gw-test:boot-1:1"  # the dedup key
    action = event["action"]
    assert action["action_type"] == "block_ip"
    assert action["target"] == "203.0.113.55"
    assert action["executor"] == "nftables"
    assert action["ttl_seconds"] == 900
    assert action["confidence"] == 0.95
    assert action["description"] == "edge.c2-egress-active tier=tier2 conf=0.95"
    assert is_executed(record(KIND_DECISION, decision_payload("execute", success=True)))


def test_held_decision_is_an_observation_event_not_an_action() -> None:
    event = event_from_record(record(KIND_DECISION, decision_payload("hold")))
    assert event is not None
    assert event["kind"] == "observation"
    assert "action" not in event
    assert event["payload"]["outcome"] == "hold"


def test_failed_apply_is_never_an_action_event() -> None:
    event = event_from_record(
        record(KIND_DECISION, decision_payload("execute", success=False))
    )
    assert event is not None
    assert event["kind"] == "observation"
    assert "action" not in event


def test_execute_failed_uploads_as_observation() -> None:
    event = event_from_record(
        record(
            KIND_EXECUTE_FAILED,
            {"reason": "no_executor_registered", "executor": "nftables"},
        )
    )
    assert event is not None
    assert event["kind"] == "observation"


def test_revert_maps_to_revert_event() -> None:
    event = event_from_record(record(KIND_REVERT, {"revert_of": 4, "success": True}))
    assert event is not None
    assert event["kind"] == "revert"


def test_offline_window_maps_as_itself() -> None:
    event = event_from_record(
        record(KIND_OFFLINE_WINDOW, {"phase": "close", "executed": []})
    )
    assert event is not None
    assert event["kind"] == "offline_window"


def test_state_transitions_are_local_only() -> None:
    assert (
        event_from_record(record(KIND_STATE, {"from": "synced", "to": "partitioned"}))
        is None
    )
    assert (
        event_from_record(record(KIND_OBSERVATION, {"raw_digest": "a" * 64}))
        is not None
    )  # observations upload


def test_batches_preserve_order_and_bounds() -> None:
    records = [record(KIND_OBSERVATION, {"i": i}) for i in range(7)]
    slices = batches(records, 3)
    assert [len(batch) for batch in slices] == [3, 3, 1]
    flat = [r.payload["i"] for batch in slices for r in batch]
    assert flat == list(range(7))
    with pytest.raises(EventMappingError):
        batches(records, 0)
