"""The drift report: what happened offline, in the analyst's vocabulary.

The spec's reconciliation step 6: "What was blocked and why (rule string +
confidence + model version), what TTLs already reverted, and which actions
still need an analyst decision." Pure function over the partition's journal
records — the reconciler calls it when the offline window closes, and the
closure record carries the payload, so the report lands in the same findings
surface the analyst already watches (plus the operator log).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.edge.journal.journal import (
    KIND_DECISION,
    KIND_EXECUTE_FAILED,
    KIND_REVERT,
    KIND_STATE,
    JournalRecord,
)


@dataclass(frozen=True)
class DriftEntry:
    """One offline event an analyst may need to act on."""

    local_sequence: int
    rule_string: str
    reason: str
    confidence: float | None
    target: str | None
    action_type: str | None
    executor: str | None
    model_id: str | None = None
    model_digest: str | None = None


@dataclass(frozen=True)
class DriftReport:
    node_id: str
    boot_id: str
    opened_at: str
    closed_at: str
    state_timeline: list[dict[str, Any]] = field(default_factory=list)
    executed: list[DriftEntry] = field(default_factory=list)
    reverted: list[DriftEntry] = field(default_factory=list)
    pending_decision: list[DriftEntry] = field(default_factory=list)
    loss_counters: dict[str, int] = field(default_factory=dict)
    evicted_ranges: list[list[int]] = field(default_factory=list)
    rejected_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def needs_analyst(self) -> bool:
        """Containment went offline unconfirmed, or evidence was lost —
        either is a human decision the report is asking for."""
        return bool(self.pending_decision or self.rejected_events or self.loss_counters)

    def to_payload(self) -> dict[str, Any]:
        """The closure record's payload — uploaded as an offline_window
        event and imported as a finding, the filterable analyst unit."""
        return {
            "phase": "close",
            "node_id": self.node_id,
            "boot_id": self.boot_id,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "state_timeline": list(self.state_timeline),
            "executed": [_entry_payload(e) for e in self.executed],
            "reverted": [_entry_payload(e) for e in self.reverted],
            "pending_decision": [_entry_payload(e) for e in self.pending_decision],
            "loss_counters": dict(self.loss_counters),
            "evicted_ranges": [list(pair) for pair in self.evicted_ranges],
            "rejected_events": list(self.rejected_events),
            "needs_analyst": self.needs_analyst,
        }

    def to_lines(self) -> list[str]:
        """The operator log's view — one line per entry, none silent."""
        lines = [
            f"drift report: node={self.node_id} window={self.opened_at}..{self.closed_at}"
        ]
        for entry in self.executed:
            lines.append(
                f"  blocked: {entry.rule_string} target={entry.target} "
                f"via={entry.executor} conf={entry.confidence} model={entry.model_id}"
            )
        for entry in self.reverted:
            lines.append(f"  reverted (TTL): {entry.rule_string} target={entry.target}")
        for entry in self.pending_decision:
            lines.append(
                f"  needs decision: {entry.rule_string} reason={entry.reason} "
                f"target={entry.target}"
            )
        if self.loss_counters:
            lines.append(f"  journal loss: {self.loss_counters}")
        if self.evicted_ranges:
            lines.append(f"  evicted ranges: {self.evicted_ranges}")
        if self.rejected_events:
            lines.append(
                f"  rejected events (never imported): {len(self.rejected_events)}"
            )
        return lines


def build_drift_report(
    records: list[JournalRecord],
    *,
    node_id: str,
    boot_id: str,
    opened_at: str,
    closed_at: str,
    loss_counters: dict[str, int] | None = None,
    evicted_ranges: list[list[int]] | None = None,
    rejected_events: list[dict[str, Any]] | None = None,
) -> DriftReport:
    """Read the partition's journal records once, in order.

    ``records`` are the window's records (everything the journal still
    holds from open to close). Holds and failed applies land in
    ``pending_decision``: an offline hold is exactly an action an analyst
    may want to take by hand; an apply that failed is containment that did
    not happen and must never be reported as if it had.
    """
    executed: list[DriftEntry] = []
    reverted: list[DriftEntry] = []
    pending: list[DriftEntry] = []
    timeline: list[dict[str, Any]] = []
    for record in records:
        payload = record.payload
        if record.kind == KIND_STATE:
            timeline.append(
                {
                    "at": record.timestamp,
                    "from": payload.get("from"),
                    "to": payload.get("to"),
                    "reason": payload.get("reason"),
                }
            )
            continue
        if record.kind == KIND_REVERT:
            reverted.append(_entry(record, payload))
            continue
        if record.kind == KIND_EXECUTE_FAILED:
            # Containment was authorized but no executor held the pair —
            # the analyst must know the block never went in.
            pending.append(
                DriftEntry(
                    local_sequence=record.local_sequence,
                    rule_string=str(payload.get("rule_string") or ""),
                    reason=f"no_executor:{payload.get('executor')}",
                    confidence=None,
                    target=payload.get("target"),
                    action_type=payload.get("action_type"),
                    executor=payload.get("executor"),
                )
            )
            continue
        if record.kind == KIND_DECISION:
            outcome = payload.get("outcome")
            entry = _entry(record, payload)
            if outcome == "execute":
                if (payload.get("execution") or {}).get("success") is True:
                    executed.append(entry)
                else:
                    pending.append(_failed_apply(entry))
            elif outcome == "hold":
                pending.append(entry)
    return DriftReport(
        node_id=node_id,
        boot_id=boot_id,
        opened_at=opened_at,
        closed_at=closed_at,
        state_timeline=timeline,
        executed=executed,
        reverted=reverted,
        pending_decision=pending,
        loss_counters=dict(loss_counters or {}),
        evicted_ranges=[list(pair) for pair in (evicted_ranges or [])],
        rejected_events=list(rejected_events or []),
    )


def _entry_payload(entry: "DriftEntry") -> dict[str, Any]:
    """Wire form of one report entry — the closure record carries these."""
    return {
        "local_sequence": entry.local_sequence,
        "rule_string": entry.rule_string,
        "reason": entry.reason,
        "confidence": entry.confidence,
        "target": entry.target,
        "action_type": entry.action_type,
        "executor": entry.executor,
        "model_id": entry.model_id,
        "model_digest": entry.model_digest,
    }


def _failed_apply(entry: "DriftEntry") -> DriftEntry:
    return DriftEntry(
        local_sequence=entry.local_sequence,
        rule_string=entry.rule_string,
        reason=f"apply_failed:{entry.reason}",
        confidence=entry.confidence,
        target=entry.target,
        action_type=entry.action_type,
        executor=entry.executor,
        model_id=entry.model_id,
        model_digest=entry.model_digest,
    )


def _entry(record: JournalRecord, payload: dict[str, Any]) -> DriftEntry:
    action = payload.get("action") or {}
    model = payload.get("model") or {}
    return DriftEntry(
        local_sequence=record.local_sequence,
        rule_string=str(payload.get("rule_string") or ""),
        reason=str(payload.get("reason") or ""),
        confidence=(
            float(payload["confidence"])
            if payload.get("confidence") is not None
            else None
        ),
        target=action.get("target") or payload.get("target"),
        action_type=action.get("action_type"),
        executor=action.get("executor"),
        model_id=model.get("id"),
        model_digest=model.get("digest"),
    )
