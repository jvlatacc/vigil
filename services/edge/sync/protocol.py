"""Journal record -> wire event: the upload contract.

The control plane understands four event kinds (core.edge.events
EVENT_KINDS): ``observation``, ``action``, ``revert``, ``offline_window``.
The journal's vocabulary is richer (decisions hold or execute; state
transitions are local bookkeeping), so the mapping is where the honest
translation happens:

- ``decision`` records that EXECUTED successfully upload as ``action``
  events — the control plane imports them into the approval pipeline as
  executed rows with edge provenance.
- ``decision`` records that held, or executed but the apply failed, upload
  as ``observation`` events carrying the full decision payload — the
  near-misses are analyst-visible (the drift report's inputs), never
  dropped, and never dressed up as containments that did not happen.
- ``execute_failed`` records (no executor registered) upload as
  ``observation`` events — recorded, never faked (the isolate_host
  precedent).
- ``revert`` records upload as ``revert`` events; ``offline_window``
  records upload as ``offline_window`` (the open marker, then the closure
  record that carries the drift summary).
- ``state`` records stay local — the offline window's payload carries the
  state timeline, so the partition's shape survives without one event per
  transition.

Every event's id is the journal record's idempotency key
(node:boot:local_sequence) — the server dedups replays on exactly it.
"""

from __future__ import annotations

from typing import Any

from services.edge.journal.journal import (
    KIND_DECISION,
    KIND_EXECUTE_FAILED,
    KIND_OBSERVATION,
    KIND_OFFLINE_WINDOW,
    KIND_REVERT,
    JournalRecord,
)

_WIRE_ACTION = "action"
_WIRE_OBSERVATION = "observation"
_WIRE_REVERT = "revert"
_WIRE_OFFLINE_WINDOW = "offline_window"

_UPLOADABLE = (
    KIND_DECISION,
    KIND_EXECUTE_FAILED,
    KIND_OBSERVATION,
    KIND_REVERT,
    KIND_OFFLINE_WINDOW,
)


class EventMappingError(ValueError):
    """A journal record the wire contract cannot express."""


def event_from_record(record: JournalRecord) -> dict[str, Any] | None:
    """The wire form of one journal record, or None for local-only kinds
    (``state``) — skipped, never silently dropped: the offline window's
    state timeline reports them at reconciliation."""
    if record.kind not in _UPLOADABLE:
        return None
    event: dict[str, Any] = {
        "event_id": record.idempotency_key(),
        "kind": _kind_for(record),
        "occurred_at": record.timestamp,
        "payload": dict(record.payload),
        "local_sequence": record.local_sequence,
    }
    if record.kind == KIND_DECISION and _executed(record):
        event["action"] = _action_object(record)
    return event


def is_executed(record: JournalRecord) -> bool:
    """True when the record evidences containment that actually took
    effect — the only journal records the control plane imports as
    approval-pipeline action rows."""
    return record.kind == KIND_DECISION and _executed(record)


def _kind_for(record: JournalRecord) -> str:
    if record.kind == KIND_DECISION:
        return _WIRE_ACTION if _executed(record) else _WIRE_OBSERVATION
    if record.kind == KIND_EXECUTE_FAILED:
        return _WIRE_OBSERVATION
    if record.kind == KIND_REVERT:
        return _WIRE_REVERT
    return _WIRE_OFFLINE_WINDOW  # KIND_OFFLINE_WINDOW


def _executed(record: JournalRecord) -> bool:
    payload = record.payload
    return (
        payload.get("outcome") == "execute"
        and isinstance(payload.get("action"), dict)
        and isinstance(payload.get("execution"), dict)
        and payload["execution"].get("success") is True
    )


def _action_object(record: JournalRecord) -> dict[str, Any]:
    """The server's action-event contract (events._validate_event):
    action_type + target required, executor/TTL/confidence carried through
    for the approval row's parameters."""
    payload = record.payload
    action = payload["action"]
    return {
        "action_type": str(action.get("action_type")),
        "target": str(action.get("target")),
        "executor": action.get("executor"),
        "ttl_seconds": action.get("ttl_seconds"),
        "confidence": payload.get("confidence"),
        "title": str(payload.get("reason") or "edge containment"),
        "description": str(payload.get("rule_string") or ""),
    }


def batches(records: list[JournalRecord], size: int) -> list[list[JournalRecord]]:
    """Bounded, in-order upload slices. Order is the spec's reconciliation
    guarantee: local-sequence order, no gaps skipped (evicted and rejected
    records are reported, never stepped over quietly)."""
    if size < 1:
        raise EventMappingError(f"batch size must be >= 1, got {size}")
    return [records[index : index + size] for index in range(0, len(records), size)]
