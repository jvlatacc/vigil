"""The append-only, hash-chained local journal (the Medic decision-record
pattern). Every record carries the sha256 of its canonical serialization
*including* the previous record's hash, so deleting, editing, or reordering
history fails verification.

Durability contract: an append is fsynced before it returns — a decision is
never lost to a crash. Sync semantics (used by the reconciliation client):
records upload in local-sequence order, ``mark_acked`` only advances on the
server's durable ack, and acked prefixes compact away — the retained segment
verifies against a persisted anchor hash, the prev-hash of its first record.

Disk bounds: the journal never grows past ``max_bytes`` if it can help it —
acked prefixes compact first, then the oldest un-acked *observation* records
evict, each eviction bumping explicit loss counters and evicted ranges that
reconciliation reports to the control plane. Visible loss, never silent
loss: containment records (decisions, reverts, window closures) are never
evicted by the budget — if protected records alone exceed the budget the
journal keeps them and reports ``over_budget`` so the operator raises the
limit instead of losing the audit trail that matters most.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64
KIND_OBSERVATION = "observation"
KIND_DECISION = "decision"
KIND_REVERT = "revert"
KIND_EXECUTE_FAILED = "execute_failed"
KIND_STATE = "state"
KIND_OFFLINE_WINDOW = "offline_window"
_PROTECTED_KINDS = frozenset(
    {KIND_DECISION, KIND_REVERT, KIND_EXECUTE_FAILED, KIND_OFFLINE_WINDOW}
)

_STATE_FILE = "acks.json"
_JOURNAL_FILE = "journal.jsonl"
_RECORD_FIELDS = (
    "local_sequence",
    "node_id",
    "boot_id",
    "timestamp",
    "kind",
    "payload",
    "prev_hash",
)


def canonical_bytes(record: dict[str, Any]) -> bytes:
    """Canonical JSON over the record fields — the hash input, and the wire
    form the control plane re-hashes at import."""
    return json.dumps(
        {key: record[key] for key in _RECORD_FIELDS},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


@dataclass(frozen=True)
class JournalRecord:
    local_sequence: int
    node_id: str
    boot_id: str
    timestamp: str
    kind: str
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str

    def idempotency_key(self) -> str:
        """node_id + boot_id + local_sequence — the server dedups replays on
        exactly this (design spec: replay is idempotent per key)."""
        return f"{self.node_id}:{self.boot_id}:{self.local_sequence}"

    def to_json(self) -> str:
        return json.dumps(
            {
                "local_sequence": self.local_sequence,
                "node_id": self.node_id,
                "boot_id": self.boot_id,
                "timestamp": self.timestamp,
                "kind": self.kind,
                "payload": self.payload,
                "prev_hash": self.prev_hash,
                "entry_hash": self.entry_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, line: str) -> JournalRecord:
        raw = json.loads(line)
        return cls(
            local_sequence=int(raw["local_sequence"]),
            node_id=str(raw["node_id"]),
            boot_id=str(raw["boot_id"]),
            timestamp=str(raw["timestamp"]),
            kind=str(raw["kind"]),
            payload=dict(raw["payload"]),
            prev_hash=str(raw["prev_hash"]),
            entry_hash=str(raw["entry_hash"]),
        )


@dataclass
class ChainReport:
    ok: bool
    checked: int
    first_bad_sequence: int | None = None


@dataclass
class _State:
    acked_upto: int = 0
    anchor: str = GENESIS_HASH
    loss_counters: dict[str, int] = field(default_factory=dict)
    evicted_ranges: list[list[int]] = field(default_factory=list)
    # Terminal local state for records the control plane refused outright
    # (shape rejections — a journal record the wire contract cannot
    # express). They never re-upload and never block window closure; the
    # drift report surfaces them every closure. Transient failures
    # ("import_failed") are NOT here — those stay unacked and retry.
    rejected: dict[str, str] = field(default_factory=dict)
    # Sequences of decision records closed by a successful revert. Durability
    # for the reaper's work queue: a successful revert record is itself
    # uploadable, so it compacts away with its ack — after which a scan of
    # live records can no longer see the closure. Without this set the next
    # compaction would resurrect the decision as pending work forever (and
    # worse, compaction would drop the pending decision before the reaper
    # ever ran, leaking the block silently).
    closed_reverts: list[int] = field(default_factory=list)


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class HashJournal:
    def __init__(
        self,
        data_dir: Path,
        *,
        node_id: str,
        boot_id: str | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        self.data_dir = data_dir
        self.node_id = node_id
        self.boot_id = boot_id or uuid.uuid4().hex
        self.max_bytes = max_bytes
        self._records: list[JournalRecord] = []
        self._state = _State()
        self.over_budget = False
        # Post-durability observer (the daemon's offline-window snapshot);
        # compaction drops acked records, so the report collects as they land.
        self.on_append: Callable[[JournalRecord], None] | None = None
        data_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    # -- paths ------------------------------------------------------------

    @property
    def journal_path(self) -> Path:
        return self.data_dir / _JOURNAL_FILE

    @property
    def state_path(self) -> Path:
        return self.data_dir / _STATE_FILE

    # -- append -------------------------------------------------------------

    def append(
        self, kind: str, payload: dict[str, Any], *, now: datetime | None = None
    ) -> JournalRecord:
        """Append one record durably (fsync before return)."""
        self._enforce_budget()
        timestamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
        record = self._build_record(
            local_sequence=self._next_sequence(),
            kind=kind,
            payload=payload,
            timestamp=timestamp,
            prev_hash=(
                self._records[-1].entry_hash if self._records else self._state.anchor
            ),
        )
        with open(self.journal_path, "a", encoding="utf-8") as handle:
            handle.write(record.to_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._records.append(record)
        # A successful revert closes its decision's pending-reaper status
        # durably (the revert record itself compacts away with its ack).
        if record.kind == KIND_REVERT and record.payload.get("success") is True:
            revert_of = record.payload.get("revert_of")
            if (
                isinstance(revert_of, int)
                and revert_of not in self._state.closed_reverts
            ):
                self._state.closed_reverts.append(revert_of)
        self._persist_state()
        if self.on_append is not None:
            # Observers run after durability: a snapshot taken for the
            # offline-window drift report never sees a record that was lost.
            self.on_append(record)
        return record

    def _next_sequence(self) -> int:
        """One past the highest sequence ever issued. The ack watermark and
        the evicted ranges count as issued even when no live record reaches
        that high: compaction retains executed-but-unreverted decisions that
        can sit BELOW the watermark, so the last live record alone would
        re-issue a sequence the server has already acked — and a record
        born behind the watermark is silently invisible to unacked(),
        never uploaded, then compacted away as if acknowledged."""
        highest = self._state.acked_upto
        if self._records:
            highest = max(highest, self._records[-1].local_sequence)
        for _, end in self._state.evicted_ranges:
            highest = max(highest, end)
        return highest + 1

    def _build_record(
        self,
        *,
        local_sequence: int,
        kind: str,
        payload: dict[str, Any],
        timestamp: str,
        prev_hash: str,
    ) -> JournalRecord:
        unsigned: dict[str, Any] = {
            "local_sequence": local_sequence,
            "node_id": self.node_id,
            "boot_id": self.boot_id,
            "timestamp": timestamp,
            "kind": kind,
            "payload": payload,
            "prev_hash": prev_hash,
        }
        entry_hash = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
        return JournalRecord(entry_hash=entry_hash, **unsigned)

    # -- bounds ---------------------------------------------------------

    def _enforce_budget(self) -> None:
        """Compact acked prefix, then evict oldest un-acked observations.
        Protected kinds are never evicted; overflow with only protected
        records raises the over_budget flag instead of losing evidence."""
        self.over_budget = False
        if self.total_bytes <= self.max_bytes:
            return
        self._compact()
        if self.total_bytes <= self.max_bytes:
            return
        evictable = [r for r in self._records if r.kind not in _PROTECTED_KINDS]
        while evictable and self.total_bytes > self.max_bytes:
            victim = evictable.pop(0)
            self._record_loss(victim)
            self._records.remove(victim)
        self._rewrite_file()
        if self.total_bytes > self.max_bytes:
            self.over_budget = True
            logger.error(
                "journal over budget with only protected records (%d bytes > %d): "
                "raise VIGIL_EDGE_JOURNAL_MAX_BYTES rather than lose containment history",
                self.total_bytes,
                self.max_bytes,
            )

    def _record_loss(self, victim: JournalRecord) -> None:
        counter = f"evicted_{victim.kind}"
        self._state.loss_counters[counter] = (
            self._state.loss_counters.get(counter, 0) + 1
        )
        start, end = victim.local_sequence, victim.local_sequence
        for existing in self._state.evicted_ranges:
            if existing[1] + 1 == start:
                existing[1] = end
                return
            if end + 1 == existing[0]:
                existing[0] = start
                return
        self._state.evicted_ranges.append([start, end])
        self._state.evicted_ranges.sort()

    @property
    def total_bytes(self) -> int:
        if not self._records:
            return 0
        return sum(len(r.to_json()) + 1 for r in self._records)

    # -- ack / compaction -------------------------------------------------

    def unacked(self) -> list[JournalRecord]:
        """Records the server has not durably acknowledged, in local-sequence
        order — the reconciliation upload list. Rejected records are
        terminal locally and never re-upload."""
        return [
            r
            for r in self._records
            if r.local_sequence > self._state.acked_upto
            and str(r.local_sequence) not in self._state.rejected
        ]

    @property
    def acked_upto(self) -> int:
        return self._state.acked_upto

    def mark_acked(self, upto: int) -> None:
        """Advance the durable-ack watermark (monotonic; the caller only
        advances after the server's durable commit) and compact the prefix."""
        if upto <= self._state.acked_upto:
            return
        self._state.acked_upto = upto
        self._compact()

    def mark_rejected(self, sequence: int, reason: str) -> None:
        """Record the control plane's terminal refusal of one record (a
        shape the wire contract cannot express). The record stops consuming
        the upload path and cannot block offline-window closure; its
        refusal stays auditable in the state file's rejection ledger and
        the drift report — the payload itself leaves the live journal when
        the ack watermark later compacts past it."""
        previous = self._state.rejected.get(str(sequence))
        self._state.rejected[str(sequence)] = reason
        if previous != reason:
            self._persist_state()

    @property
    def rejected(self) -> list[dict[str, Any]]:
        """The rejection ledger for the drift report: what the control
        plane refused and why, so nothing disappears quietly."""
        return [
            {"local_sequence": int(seq), "reason": reason}
            for seq, reason in sorted(
                self._state.rejected.items(), key=lambda kv: int(kv[0])
            )
        ]

    def _compact(self) -> None:
        """Drop the acked prefix from memory and disk; the retained segment's
        first record keeps its prev_hash as the persisted verification anchor.

        One retention rule outranks the ack: an executed-but-unreverted
        decision is pending reaper work, not uploaded history. Sync acks in
        seconds and TTLs run in minutes — dropping executed decisions at ack
        time would erase the reaper's work queue in the normal connected
        case and leak the block silently. The decision compacts once the
        successful revert closes it (closed_reverts)."""
        closed = self._successful_revert_seqs()

        def _retained(record: JournalRecord) -> bool:
            if record.local_sequence > self._state.acked_upto:
                return True
            if record.kind != KIND_DECISION:
                return False
            payload = record.payload
            if payload.get("outcome") != "execute":
                return False
            execution = payload.get("execution") or {}
            if execution.get("success") is not True:
                return False
            return record.local_sequence not in closed

        remaining = [r for r in self._records if _retained(r)]
        if len(remaining) == len(self._records):
            return
        self._state.anchor = remaining[0].prev_hash if remaining else GENESIS_HASH
        self._records = remaining
        self._rewrite_file()

    def _rewrite_file(self) -> None:
        tmp = self.journal_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.writelines(record.to_json() + "\n" for record in self._records)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.journal_path)
        self._persist_state()

    # -- caps (the gate's CapsView) ----------------------------------------

    def _successful_revert_seqs(self) -> set[int]:
        """Local sequences of decision records closed by a successful
        revert. Failed reverts deliberately do not appear: the work stays
        pending until the revert is real. The persisted set outranks the
        scan — a closed revert record compacts away with its ack, and the
        scan of live records alone would then resurrect the decision as
        pending forever."""
        closed: set[int] = set(self._state.closed_reverts)
        for record in self._records:
            if record.kind != KIND_REVERT:
                continue
            if record.payload.get("success") is not True:
                continue
            revert_of = record.payload.get("revert_of")
            if isinstance(revert_of, int):
                closed.add(revert_of)
        return closed

    def _executed_decisions(self) -> list[tuple[JournalRecord, dict[str, Any]]]:
        """Decision records that actually took effect: outcome=execute with a
        successful executor apply. Failed applies bound nothing — only real
        containment consumes a cap."""
        executed = []
        for record in self._records:
            if record.kind != KIND_DECISION:
                continue
            payload = record.payload
            if payload.get("outcome") != "execute":
                continue
            execution = payload.get("execution") or {}
            if execution.get("success") is not True:
                continue
            executed.append((record, payload))
        return executed

    def executed_in_last_hour(self, action_type: str, now: datetime) -> int:
        """Executed actions of this type in (now-1h, now] — the bundle's
        per-hour cap input."""
        count = 0
        for record, payload in self._executed_decisions():
            action = payload.get("action") or {}
            if action.get("action_type") != action_type:
                continue
            ts = _parse_ts(record.timestamp)
            if ts is None:
                continue
            if now - timedelta(hours=1) < ts <= now:
                count += 1
        return count

    def active_blocks(self, now: datetime) -> int:
        """Executed blocks whose TTL has not expired and that no successful
        revert has closed — the bundle's max-active-blocks cap input."""
        reverted = self._successful_revert_seqs()
        active = 0
        for record, payload in self._executed_decisions():
            if record.local_sequence in reverted:
                continue
            action = payload.get("action") or {}
            ttl = action.get("ttl_seconds")
            ts = _parse_ts(record.timestamp)
            if ts is None or not isinstance(ttl, int):
                continue
            if ts <= now < ts + timedelta(seconds=ttl):
                active += 1
        return active

    def pending_reverts(
        self, now: datetime
    ) -> list[tuple[JournalRecord, dict[str, Any]]]:
        """Executed blocks whose TTL has expired and that no successful
        revert has closed — the TTL reaper's work queue. The queue is
        derived from durable journal history, so it survives restarts: a
        block whose process died mid-TTL is still reaped after reboot.
        Failed reverts stay here until a revert actually succeeds."""
        reverted = self._successful_revert_seqs()
        pending: list[tuple[JournalRecord, dict[str, Any]]] = []
        for record, payload in self._executed_decisions():
            if record.local_sequence in reverted:
                continue
            ref = (payload.get("execution") or {}).get("ref")
            if not isinstance(ref, str) or not ref:
                continue
            action = payload.get("action") or {}
            ttl = action.get("ttl_seconds")
            ts = _parse_ts(record.timestamp)
            if ts is None or not isinstance(ttl, int):
                continue
            if now >= ts + timedelta(seconds=ttl):
                pending.append((record, payload))
        return pending

    # -- verification ------------------------------------------------------

    def verify_chain(self) -> ChainReport:
        """Recompute every hash and the linkage. The first record verifies
        against the persisted anchor (its predecessor may be compacted away);
        every later record must reference its actual predecessor."""
        previous_hash = self._state.anchor
        checked = 0
        for record in self._records:
            unsigned = {
                "local_sequence": record.local_sequence,
                "node_id": record.node_id,
                "boot_id": record.boot_id,
                "timestamp": record.timestamp,
                "kind": record.kind,
                "payload": record.payload,
                "prev_hash": record.prev_hash,
            }
            if record.prev_hash != previous_hash:
                return ChainReport(
                    ok=False, checked=checked, first_bad_sequence=record.local_sequence
                )
            if (
                hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
                != record.entry_hash
            ):
                return ChainReport(
                    ok=False, checked=checked, first_bad_sequence=record.local_sequence
                )
            previous_hash = record.entry_hash
            checked += 1
        return ChainReport(ok=True, checked=checked)

    # -- loss reporting (reconciliation consumes these) --------------------

    @property
    def loss_counters(self) -> dict[str, int]:
        return dict(self._state.loss_counters)

    @property
    def evicted_ranges(self) -> list[list[int]]:
        return [list(pair) for pair in self._state.evicted_ranges]

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        if self.state_path.exists():
            try:
                raw = json.loads(self.state_path.read_text())
                self._state = _State(
                    acked_upto=int(raw.get("acked_upto", 0)),
                    anchor=str(raw.get("anchor", GENESIS_HASH)),
                    loss_counters=dict(raw.get("loss_counters", {})),
                    evicted_ranges=[
                        list(pair) for pair in raw.get("evicted_ranges", [])
                    ],
                    rejected={
                        str(seq): str(reason)
                        for seq, reason in raw.get("rejected", {}).items()
                    },
                    closed_reverts=[int(seq) for seq in raw.get("closed_reverts", [])],
                )
            except (OSError, ValueError) as exc:
                logger.error(
                    "journal state unreadable (%s): %s — assuming fresh",
                    self.state_path,
                    exc,
                )
                self._state = _State()
        if not self.journal_path.exists():
            return
        try:
            lines = self.journal_path.read_text().splitlines()
            self._records = [
                JournalRecord.from_json(line) for line in lines if line.strip()
            ]
        except (OSError, ValueError) as exc:
            # A tampered or truncated journal is quarantined, never trusted:
            # the chain check would fail for every later record anyway.
            quarantine = self.journal_path.with_suffix(".corrupt")
            os.replace(self.journal_path, quarantine)
            logger.error("journal unreadable, quarantined to %s: %s", quarantine, exc)
            self._records = []
            return
        report = self.verify_chain()
        if not report.ok:
            quarantine = self.journal_path.with_suffix(".corrupt")
            os.replace(self.journal_path, quarantine)
            logger.error(
                "journal chain broken at sequence %s, quarantined to %s",
                report.first_bad_sequence,
                quarantine,
            )
            self._records = []

    def _persist_state(self) -> None:
        payload = json.dumps(
            {
                "acked_upto": self._state.acked_upto,
                "anchor": self._state.anchor,
                "loss_counters": self._state.loss_counters,
                "evicted_ranges": self._state.evicted_ranges,
                "rejected": self._state.rejected,
                "closed_reverts": self._state.closed_reverts,
            },
            sort_keys=True,
        )
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(payload)
        os.replace(tmp, self.state_path)
