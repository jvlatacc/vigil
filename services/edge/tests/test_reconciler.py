"""Reconciliation: the pure watermark rule, then bounded replay against a
fake client - acks only after durable commit, in-order batches, idempotent
replay, terminal rejections quarantined."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from services.edge.journal.journal import KIND_OBSERVATION, KIND_STATE, HashJournal
from services.edge.sync.client import SyncError
from services.edge.sync.reconciler import Reconciler, advance_watermark

# -- the pure watermark rule ------------------------------------------------


def pairs(*sequences: int) -> list[tuple[int, str]]:
    return [(seq, f"node:boot:{seq}") for seq in sequences]


def response(
    acked: list[str] | None = None,
    duplicates: list[str] | None = None,
    rejected: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "acked": acked or [],
        "duplicates": duplicates or [],
        "rejected": rejected or [],
    }


def test_full_commit_advances_to_the_last_sequence() -> None:
    watermark, terminal = advance_watermark(
        pairs(1, 2, 3),
        response(acked=["node:boot:1", "node:boot:2", "node:boot:3"]),
    )
    assert watermark == 3
    assert terminal == []


def test_duplicates_are_durable_commits() -> None:
    watermark, _ = advance_watermark(
        pairs(1, 2), response(duplicates=["node:boot:1", "node:boot:2"])
    )
    assert watermark == 2


def test_a_gap_stalls_the_watermark_behind_the_uncommitted_record() -> None:
    watermark, _ = advance_watermark(
        pairs(1, 2, 3), response(acked=["node:boot:1", "node:boot:3"])
    )
    assert watermark == 1  # seq 2 never commits; advancing past it would drop it


def test_terminal_rejection_quarantines_without_stalling() -> None:
    watermark, terminal = advance_watermark(
        pairs(1, 2, 3),
        response(
            acked=["node:boot:1", "node:boot:3"],
            rejected=[
                {"event_id": "node:boot:2", "reason": "schema_version_unsupported"}
            ],
        ),
    )
    assert watermark == 3  # rejected record is terminal, not a retry stall
    assert terminal == [(2, "schema_version_unsupported")]


def test_transient_import_failed_stalls() -> None:
    watermark, terminal = advance_watermark(
        pairs(1, 2),
        response(rejected=[{"event_id": "node:boot:1", "reason": "import_failed"}]),
    )
    assert watermark is None
    assert terminal == []  # retried next cycle, never quarantined


# -- the reconciler against a fake client -----------------------------------


class FakeClient:
    """Scripted post_events responses; records every upload for replay
    assertions."""

    def __init__(self, responses: list[dict | Exception]) -> None:
        self.responses = list(responses)
        self.uploads: list[list[dict]] = []

    async def post_events(self, events: list[dict]) -> dict:
        self.uploads.append(events)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_journal(tmp_path: Path, node_id: str = "gw-test") -> HashJournal:
    return HashJournal(tmp_path / "journal", node_id=node_id, boot_id="boot-1")


def observation_records(journal: HashJournal, count: int) -> list:
    return [journal.append(KIND_OBSERVATION, {"i": i}) for i in range(count)]


def ids_of(events: list[dict]) -> list[str]:
    return [event["event_id"] for event in events]


def event_id(seq: int) -> str:
    return f"gw-test:boot-1:{seq}"


def test_batches_upload_in_order_and_bounded(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    observation_records(journal, 5)
    all_acked = response(acked=[event_id(i) for i in range(1, 6)])
    client = FakeClient([all_acked, all_acked, all_acked])
    reconciler = Reconciler(client, journal, batch_size=2)

    drained = asyncio.run(reconciler.reconcile())

    assert drained is True
    assert [len(upload) for upload in client.uploads] == [2, 2, 1]
    assert ids_of(client.uploads[0]) == [event_id(1), event_id(2)]
    assert ids_of(client.uploads[2]) == [event_id(5)]
    assert journal.acked_upto == 5


def test_ack_only_lands_after_the_durable_response(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    observation_records(journal, 2)
    client = FakeClient([SyncError("cable pulled")])
    reconciler = Reconciler(client, journal, batch_size=10)

    with pytest.raises(SyncError):
        asyncio.run(reconciler.reconcile())

    assert journal.acked_upto == 0  # nothing marked acked on a failed call
    assert len(journal.unacked()) == 2  # both records wait for the next cycle


def test_failed_batch_replays_the_same_event_ids(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    observation_records(journal, 3)
    client = FakeClient(
        [
            SyncError("dropped"),
            response(acked=[event_id(1), event_id(2), event_id(3)]),
        ]
    )
    reconciler = Reconciler(client, journal, batch_size=10)

    with pytest.raises(SyncError):
        asyncio.run(reconciler.reconcile())
    drained = asyncio.run(reconciler.reconcile())

    assert drained is True
    assert ids_of(client.uploads[0]) == ids_of(client.uploads[1])
    assert journal.acked_upto == 3


def test_local_only_slices_ack_through_without_uploading(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    journal.append(KIND_STATE, {"from": "synced", "to": "partitioned"})
    journal.append(KIND_STATE, {"from": "partitioned", "to": "reconciling"})
    client = FakeClient([])
    reconciler = Reconciler(client, journal, batch_size=10)

    drained = asyncio.run(reconciler.reconcile())

    assert drained is True
    assert client.uploads == []  # state transitions never upload
    assert journal.acked_upto == 2


def test_server_that_never_acks_leaves_work_for_the_next_cycle(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    observation_records(journal, 4)
    empty = response()
    client = FakeClient([empty] * 64)  # every round acks nothing
    reconciler = Reconciler(client, journal, batch_size=2)

    drained = asyncio.run(reconciler.reconcile())

    assert drained is False  # bounded rounds; the next cycle continues
    assert journal.acked_upto == 0
    assert len(journal.unacked()) == 4


def test_terminal_rejections_are_quarantined_and_never_reuploaded(
    tmp_path: Path,
) -> None:
    journal = make_journal(tmp_path)
    observation_records(journal, 3)
    client = FakeClient(
        [
            response(
                acked=[event_id(1)],
                rejected=[{"event_id": event_id(2), "reason": "shape_refused"}],
            ),
            response(acked=[event_id(3)]),
        ]
    )
    reconciler = Reconciler(client, journal, batch_size=10)

    drained = asyncio.run(reconciler.reconcile())

    assert drained is True
    assert journal.acked_upto == 3  # the watermark passes the rejected record
    assert journal.rejected == [{"local_sequence": 2, "reason": "shape_refused"}]
    assert len(journal.unacked()) == 0
    # The quarantined record never uploads again (nothing left unacked).
    assert ids_of(client.uploads[1]) == [event_id(3)]
