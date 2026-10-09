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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64
KIND_OBSERVATION = "observation"
KIND_DECISION = "decision"
KIND_REVERT = "revert"
KIND_OFFLINE_WINDOW = "offline_window"
_PROTECTED_KINDS = frozenset({KIND_DECISION, KIND_REVERT, KIND_OFFLINE_WINDOW})

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
        self._persist_state()
        return record

    def _next_sequence(self) -> int:
        if self._records:
            return self._records[-1].local_sequence + 1
        return self._state.acked_upto + 1

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
        order — the reconciliation upload list."""
        return [r for r in self._records if r.local_sequence > self._state.acked_upto]

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

    def _compact(self) -> None:
        """Drop the acked prefix from memory and disk; the retained segment's
        first record keeps its prev_hash as the persisted verification anchor."""
        remaining = [
            r for r in self._records if r.local_sequence > self._state.acked_upto
        ]
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
            },
            sort_keys=True,
        )
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(payload)
        os.replace(tmp, self.state_path)
