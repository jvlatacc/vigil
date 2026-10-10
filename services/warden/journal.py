"""Warden's decision journal: hash-chained JSONL, tamper-evident on read.

Every decision Warden makes — enforced or refused — is recorded here while
the control plane may be unreachable; on reconnect the reconciler pushes
these records and the server verifies the same chain. The formula is the
agent_events pattern via core/edge/journal.record_hash:
sha256(prev_hash ‖ record) over the canonical RECORD_FIELDS, with the
first record chaining from GENESIS_PREV_HASH.

Failure posture:
- **Poisoned, never extended.** A middle line that fails to parse, a seq
  gap, or a broken hash link poisons the journal; appends raise rather
  than write onto an untrustworthy base. The file is kept for forensics.
- **Torn tail is quarantined, not hidden.** A crash mid-append can leave
  an unparseable final line; the intact prefix keeps verifying, so the
  torn line is moved to ``<journal>.torn`` and the chain continues. Data
  is moved aside, never deleted.
- The in-memory image equals the verified on-disk prefix: seqs are
  contiguous from 1, each prev_hash matches, and records_after() hands
  the reconciler exactly what it can push.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.edge.journal import GENESIS_PREV_HASH, RECORD_FIELDS, record_hash

logger = logging.getLogger(__name__)


class JournalPoisonedError(RuntimeError):
    """The journal's chain is untrustworthy; appends are refused."""


@dataclass(frozen=True)
class JournalStatus:
    poisoned: bool
    reason: str
    head_seq: int
    head_hash: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "poisoned": self.poisoned,
            "reason": self.reason,
            "last_seq": self.head_seq,
            "head": self.head_hash,
        }


def _record_line(record: dict[str, Any]) -> bytes:
    return (json.dumps(record, separators=(",", ":")) + "\n").encode()


class Journal:
    """Append-only decision journal with startup chain verification."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._records: list[dict[str, Any]] = []
        self._poison_reason = ""
        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Verify the file into the in-memory image, quarantining a torn tail."""
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(self._path.parent, 0o700)
            return
        except OSError as exc:
            self._poison(f"journal unreadable: {exc}")
            return

        lines = raw.decode().splitlines()
        if lines and lines[-1] == "":
            lines.pop()
        parsed: list[dict[str, Any]] = []
        prev = GENESIS_PREV_HASH
        for index, line in enumerate(lines):
            try:
                record = json.loads(line)
            except ValueError:
                if index == len(lines) - 1:
                    self._quarantine_torn_tail(parsed)
                    break  # intact prefix stands
                self._poison(f"line {index + 1} is not JSON")
                return
            if not self._verify_link(record, parsed, prev, index):
                return
            parsed.append(record)
            prev = record_hash(record["prev_hash"], record)
        self._records = parsed

    def _verify_link(
        self,
        record: Any,
        parsed: list[dict[str, Any]],
        prev: str,
        index: int,
    ) -> bool:
        where = f"journal line {index + 1}"
        if not isinstance(record, dict):
            self._poison(f"{where} is not a record object")
            return False
        keys = set(record)
        if not set(RECORD_FIELDS) | {"prev_hash"} <= keys:
            self._poison(f"{where} is missing required fields")
            return False
        if keys - set(RECORD_FIELDS) - {"prev_hash"}:
            # Unknown keys hash as nothing but must never ride on a record:
            # the wire model forbids extras, so the loader does too.
            self._poison(f"{where} carries unknown fields")
            return False
        expected_seq = len(parsed) + 1
        if record["seq"] != expected_seq:
            self._poison(f"{where} has seq {record['seq']}, expected {expected_seq}")
            return False
        if record["prev_hash"] != prev:
            self._poison(f"{where} does not chain from the previous record")
            return False
        return True

    def _quarantine_torn_tail(self, prefix: list[dict[str, Any]]) -> None:
        """Move the final, unparseable line aside; keep it for forensics."""
        torn = self._path.with_suffix(self._path.suffix + ".torn")
        logger.error(
            "warden journal: final line was torn (crash mid-write); moved to %s", torn
        )
        try:
            os.replace(self._path, torn)
            fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as handle:
                for record in prefix:
                    handle.write(_record_line(record))
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            self._poison(f"could not quarantine the torn final line: {exc}")
            return
        # The intact prefix is now the file; keep it as the in-memory image.
        self._records = prefix

    def _poison(self, reason: str) -> None:
        self._poison_reason = reason
        self._records = []
        logger.error("warden journal POISONED: %s — appends refused", reason)

    # ------------------------------------------------------------------
    # Appending
    # ------------------------------------------------------------------

    def append(
        self,
        *,
        mode: str,
        idempotency_key: str,
        action_type: str,
        target: str,
        decision_rule: str,
        execution: dict[str, Any],
        ts: str,
    ) -> dict[str, Any]:
        """Append one decision record; returns the record as written."""
        if self._poison_reason:
            raise JournalPoisonedError(self._poison_reason)
        record: dict[str, Any] = {
            "seq": len(self._records) + 1,
            "ts": ts,
            "mode": mode,
            "idempotency_key": idempotency_key,
            "action_type": action_type,
            "target": target,
            "decision_rule": decision_rule,
            "execution": execution,
        }
        prev = (
            record_hash(self._records[-1]["prev_hash"], self._records[-1])
            if self._records
            else GENESIS_PREV_HASH
        )
        record["prev_hash"] = prev
        self._append_line(record)
        self._records.append(record)
        return record

    def _append_line(self, record: dict[str, Any]) -> None:
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, _record_line(record))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(self._path, 0o600)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def status(self) -> JournalStatus:
        head_hash = None
        if self._records:
            head = self._records[-1]
            head_hash = record_hash(head["prev_hash"], head)
        return JournalStatus(
            poisoned=bool(self._poison_reason),
            reason=self._poison_reason,
            head_seq=len(self._records),
            head_hash=head_hash,
        )

    def records_after(self, seq: int) -> list[dict[str, Any]]:
        """Verified records with seq greater than ``seq``, in order."""
        return [record for record in self._records if record["seq"] > seq]
