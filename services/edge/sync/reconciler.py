"""Reconciliation: bounded replay, contiguous durable acks.

The spec's reconciliation sequence, as one method: watermark exchange
(the heartbeat carries it), bounded in-order batch uploads, ack only after
the server's durable commit, and a drained-journal verdict the daemon uses
to close the offline window.

Two facts carry the design:

- **Contiguity is computed client-side.** The server acks per event
  (``acked`` + ``duplicates`` are durable commits; ``rejected`` entries
  name the reason). A record the server refused outright ("import_failed"
  aside) is terminal locally; a transient failure keeps its place — and
  the durable watermark never advances past it, because advancing over an
  uncommitted record would silently drop it on compaction.
- **Rounds are bounded.** A server that acks without ever draining the
  journal cannot spin one cycle forever; leftover work simply waits for
  the next cycle's backoff.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Protocol

from services.edge.journal.journal import HashJournal
from services.edge.sync.protocol import batches, event_from_record

logger = logging.getLogger(__name__)

#: Bounded upload rounds per reconciliation cycle. Reaching it is not an
#: error — the next cycle continues where the watermark stopped.
_MAX_UPLOAD_ROUNDS = 64

#: The server's transient per-event refusal: retried, never quarantined.
_IMPORT_FAILED = "import_failed"


def advance_watermark(
    pairs: list[tuple[int, str]], response: Mapping[str, Any]
) -> tuple[int | None, list[tuple[int, str]]]:
    """The pure core of the durable-ack rule.

    ``pairs`` are (local_sequence, event_id) in upload order; ``response``
    is the server's {acked, duplicates, rejected}. Returns the contiguous
    durable watermark — every record at or below it is committed or
    terminally rejected — plus the terminal rejections to quarantine.

    A committed event beyond a stalled one never advances the watermark
    (that would mark the stalled record as acked and compact it away
    unuploaded); its commit is durable server-side, and replay closes the
    gap when it comes back a duplicate.
    """
    committed = set(response.get("acked") or []) | set(response.get("duplicates") or [])
    rejections = {
        entry.get("event_id"): entry.get("reason", "")
        for entry in (response.get("rejected") or [])
        if isinstance(entry, dict)
    }
    watermark: int | None = None
    stalled = False
    terminal: list[tuple[int, str]] = []
    for sequence, event_id in pairs:
        reason = rejections.get(event_id)
        if reason is not None and reason != _IMPORT_FAILED:
            terminal.append((sequence, reason))
            continue
        if stalled or event_id not in committed:
            stalled = True
            continue
        watermark = sequence
    return watermark, terminal


class EventUploader(Protocol):
    """The one method of the sync client the reconciler drives."""

    async def post_events(self, events: list[dict]) -> dict: ...


class Reconciler:
    """Uploads the journal's unacked records; owns nothing else.

    The daemon supplies the client and journal, reads the drained verdict,
    and handles states, windows, and the drift report.
    """

    def __init__(
        self,
        client: EventUploader,
        journal: HashJournal,
        *,
        batch_size: int,
    ) -> None:
        self._client = client
        self._journal = journal
        self._batch_size = batch_size

    async def reconcile(self) -> bool:
        """Upload unacked records in bounded, in-order batches until the
        journal drains. True = drained (nothing unacked remains); False =
        rounds exhausted with work left (retry next cycle). A failed call
        raises :class:`SyncError` — the daemon turns that into PARTITIONED.

        Local-only records (state transitions) never upload; when a slice
        is all local-only, the watermark moves through them here: they are
        journal bookkeeping, already reflected in the offline-window
        payload they predate.
        """
        for _ in range(_MAX_UPLOAD_ROUNDS):
            records = self._journal.unacked()
            if not records:
                return True
            batch = records[: self._batch_size]
            events: list[dict[str, Any]] = []
            pairs: list[tuple[int, str]] = []
            for record in batch:
                event = event_from_record(record)
                if event is None:
                    continue
                events.append(event)
                pairs.append((record.local_sequence, str(event["event_id"])))
            if not events:
                self._journal.mark_acked(batch[-1].local_sequence)
                continue
            response = await self._client.post_events(events)
            self._apply_response(pairs, response)
        return not self._journal.unacked()

    def _apply_response(
        self, pairs: list[tuple[int, str]], response: Mapping[str, Any]
    ) -> None:
        watermark, terminal = advance_watermark(pairs, response)
        for sequence, reason in terminal:
            logger.warning(
                "journal record %s rejected by control plane (%s) — quarantined",
                sequence,
                reason,
            )
            self._journal.mark_rejected(sequence, reason)
        if watermark is not None:
            self._journal.mark_acked(watermark)

    def pending_count(self) -> int:
        return len(self._journal.unacked())

    def pending_batches(self) -> int:
        return len(batches(self._journal.unacked(), self._batch_size))
