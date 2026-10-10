"""Journal suite: hash-chain construction and tamper detection, the
node_id+boot_id+local_sequence idempotency key, durable-ack compaction,
and bounded eviction with explicit loss counters — never silent discard."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from services.edge.journal.journal import (
    GENESIS_HASH,
    KIND_DECISION,
    KIND_OBSERVATION,
    KIND_REVERT,
    HashJournal,
)

NODE_ID = "gw-vpc-west-01"
BOOT_ID = "boot-abc123"


def make_journal(tmp_path: Path, **kwargs) -> HashJournal:
    return HashJournal(tmp_path, node_id=NODE_ID, boot_id=BOOT_ID, **kwargs)


def test_append_builds_prev_hash_chain(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    first = journal.append(KIND_OBSERVATION, {"flow": "a"})
    second = journal.append(KIND_DECISION, {"block": "203.0.113.5"})
    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.entry_hash
    report = journal.verify_chain()
    assert report.ok
    assert report.checked == 2


def test_idempotency_key_is_node_boot_sequence(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    record = journal.append(KIND_OBSERVATION, {"flow": "a"})
    assert record.idempotency_key() == f"{NODE_ID}:{BOOT_ID}:1"


def test_sequences_continue_after_reload(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    journal.append(KIND_OBSERVATION, {"n": 1})
    journal.append(KIND_OBSERVATION, {"n": 2})

    reloaded = make_journal(tmp_path)
    unacked = reloaded.unacked()
    assert [r.local_sequence for r in unacked] == [1, 2]
    assert reloaded.verify_chain().ok
    third = reloaded.append(KIND_OBSERVATION, {"n": 3})
    assert third.local_sequence == 3


def test_tampered_record_fails_chain_and_quarantines(tmp_path: Path) -> None:
    """Flip one byte in a stored record: reload detects the broken chain,
    quarantines the file, and starts clean rather than trusting tampered
    history."""
    journal = make_journal(tmp_path)
    for n in range(3):
        journal.append(KIND_OBSERVATION, {"n": n})
    journal_path = tmp_path / "journal.jsonl"

    lines = journal_path.read_text().splitlines()
    tampered = json.loads(lines[1])
    tampered["payload"]["n"] = 999
    lines[1] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
    journal_path.write_text("\n".join(lines) + "\n")

    reloaded = make_journal(tmp_path)
    assert reloaded.unacked() == []  # quarantined: nothing trusted
    assert (tmp_path / "journal.corrupt").exists()


def test_mark_acked_compacts_prefix_keeps_chain(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    for n in range(5):
        journal.append(KIND_OBSERVATION, {"n": n})
    journal.mark_acked(3)
    assert journal.acked_upto == 3
    assert [r.local_sequence for r in journal.unacked()] == [4, 5]
    assert journal.verify_chain().ok

    reloaded = make_journal(tmp_path)
    assert reloaded.acked_upto == 3
    assert [r.local_sequence for r in reloaded.unacked()] == [4, 5]
    assert reloaded.verify_chain().ok


def test_mark_acked_is_monotonic(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    journal.append(KIND_OBSERVATION, {"n": 1})
    journal.mark_acked(1)
    journal.mark_acked(1)  # no-op, not a rewind
    journal.mark_acked(0)
    assert journal.acked_upto == 1


def test_overflow_evicts_observations_with_loss_counters(tmp_path: Path) -> None:
    journal = make_journal(tmp_path, max_bytes=1024)
    for n in range(5):
        journal.append(KIND_OBSERVATION, {"n": n, "padding": "x" * 120})
    assert journal.loss_counters.get("evicted_observation", 0) >= 1
    assert journal.evicted_ranges, "evicted ranges must be explicit, never silent"
    first_evicted = journal.evicted_ranges[0][0]
    assert first_evicted == 1  # oldest goes first
    remaining = {r.local_sequence for r in journal.unacked()}
    for start, end in journal.evicted_ranges:
        assert not (set(range(start, end + 1)) & remaining)


def test_containment_records_survive_overflow(tmp_path: Path) -> None:
    journal = make_journal(tmp_path, max_bytes=1024)
    journal.append(KIND_DECISION, {"block_ip": "203.0.113.9", "padding": "y" * 200})
    for n in range(4):
        journal.append(KIND_OBSERVATION, {"n": n, "padding": "x" * 120})
    decisions = [r for r in journal.unacked() if r.kind == KIND_DECISION]
    assert len(decisions) == 1, "budget pressure may never evict containment history"


def test_protected_only_overflow_sets_flag_not_loss(tmp_path: Path) -> None:
    journal = make_journal(tmp_path, max_bytes=256)
    for n in range(3):
        journal.append(KIND_DECISION, {"n": n, "padding": "z" * 150})
    assert journal.over_budget
    assert journal.loss_counters == {}
    assert len(journal.unacked()) == 3  # kept, reported, never dropped


def test_loss_state_persists_across_boot(tmp_path: Path) -> None:
    journal = make_journal(tmp_path, max_bytes=1024)
    for n in range(5):
        journal.append(KIND_OBSERVATION, {"n": n, "padding": "x" * 120})
    lost = journal.loss_counters
    ranges = journal.evicted_ranges
    assert lost

    reloaded = make_journal(tmp_path)
    assert reloaded.loss_counters == lost
    assert reloaded.evicted_ranges == ranges


def test_eviction_ranges_merge_contiguous(tmp_path: Path) -> None:
    journal = make_journal(tmp_path, max_bytes=1024)
    for n in range(5):
        journal.append(KIND_OBSERVATION, {"n": n, "padding": "x" * 120})
    # Sequences 1..K evicted in order — one merged range, not K fragments.
    assert len(journal.evicted_ranges) == 1
    start, end = journal.evicted_ranges[0]
    assert start == 1 and end >= 1


# -- compaction vs the reaper's work queue ---------------------------------
# Sync acks in seconds and TTLs run in minutes: if ack-compaction dropped
# executed decisions, the reaper's journal-derived queue would empty in the
# normal connected case and blocks would leak past their TTL silently.


def _executed_decision_payload(ip: str = "203.0.113.9") -> dict:
    return {
        "outcome": "execute",
        "decision_rule": f"edge.c2-egress tier=tier2 conf=0.95 target={ip}",
        "actor": f"edge:{NODE_ID}@v1",
        "action": {
            "action_type": "block_ip",
            "executor": "nftables",
            "target": ip,
            "ttl_seconds": 5,
        },
        "execution": {"success": True, "ref": f"blk-{ip}"},
    }


def _revert_payload(decision_seq: int, *, success: bool) -> dict:
    return {
        "revert_of": decision_seq,
        "success": success,
        "ref": "blk-203.0.113.9",
        "executor": "nftables",
        "target": "203.0.113.9",
        "actor": "edge:ttl-reaper",
    }


def _expired(now: datetime) -> datetime:
    return now + timedelta(seconds=30)


def test_compaction_retains_executed_decision_until_reverted(
    tmp_path: Path,
) -> None:
    journal = make_journal(tmp_path)
    journal.append(KIND_OBSERVATION, {"n": 1})
    decision = journal.append(KIND_DECISION, _executed_decision_payload())
    journal.mark_acked(decision.local_sequence)

    # The ack compacts the observation but keeps the pending block: the
    # reaper's work queue is derived from the journal, and the block's TTL
    # has not expired yet, let alone been reverted.
    pending = journal.pending_reverts(_expired(datetime.now(UTC)))
    assert [r.local_sequence for r, _ in pending] == [decision.local_sequence]
    assert journal.verify_chain().ok

    # And it survives reload — the retained segment is durable, so a daemon
    # that restarts mid-TTL still reaps the block.
    reloaded = make_journal(tmp_path)
    pending = reloaded.pending_reverts(_expired(datetime.now(UTC)))
    assert [r.local_sequence for r, _ in pending] == [decision.local_sequence]
    assert reloaded.verify_chain().ok


def test_successful_revert_lets_compaction_drop_both(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    decision = journal.append(KIND_DECISION, _executed_decision_payload())
    revert = journal.append(
        KIND_REVERT, _revert_payload(decision.local_sequence, success=True)
    )
    journal.mark_acked(revert.local_sequence)

    assert journal.pending_reverts(_expired(datetime.now(UTC))) == []
    # Both records are acked and closed: the next compaction drops them.
    reloaded = make_journal(tmp_path)
    assert reloaded.unacked() == []
    assert reloaded.verify_chain().ok


def test_revert_closure_persists_in_state_not_records(tmp_path: Path) -> None:
    """The closure must outlive the revert record itself: once that record
    compacts away, a live-record scan can no longer see the revert, and a
    scan-only implementation resurrects the decision as pending forever."""
    journal = make_journal(tmp_path)
    decision = journal.append(KIND_DECISION, _executed_decision_payload())
    revert = journal.append(
        KIND_REVERT, _revert_payload(decision.local_sequence, success=True)
    )
    journal.mark_acked(revert.local_sequence)

    state = json.loads((tmp_path / "acks.json").read_text())
    assert decision.local_sequence in state["closed_reverts"]

    reloaded = make_journal(tmp_path)
    # The decision record is gone (compacted), but the durable closure set
    # still knows it: a replay that somehow re-presents the decision cannot
    # resurrect it as reaper work.
    assert decision.local_sequence in reloaded._successful_revert_seqs()


def test_sequence_floors_at_ack_watermark_after_retention(
    tmp_path: Path,
) -> None:
    """A retained decision below the watermark must not cause the next
    append to reuse an acked sequence: the record would be born invisible
    to unacked() and later compacted away without ever uploading — the
    offline-window closure was lost exactly this way."""
    journal = make_journal(tmp_path)
    journal.append(KIND_OBSERVATION, {"n": 1})  # seq 1
    decision = journal.append(KIND_DECISION, _executed_decision_payload())  # seq 2
    journal.mark_acked(decision.local_sequence)  # watermark 2, decision retained

    # A local-only state record advances the watermark past the retained
    # decision (the reconciler marks local-only slices acked in place).
    journal.append(KIND_OBSERVATION, {"n": 2})  # seq 3, unacked
    journal.mark_acked(3)  # watermark 3 > retained decision's seq 2

    closing = journal.append(KIND_REVERT, _revert_payload(2, success=True))
    assert closing.local_sequence > 3  # must not reuse seq 2 or 3
    assert closing.idempotency_key() != f"{NODE_ID}:{BOOT_ID}:2"

    # The closure is unacked and will upload; the retained decision is now
    # closed and the next compaction drops both.
    assert [r.local_sequence for r in journal.unacked()] == [closing.local_sequence]
    journal.mark_acked(closing.local_sequence)
    assert journal.pending_reverts(_expired(datetime.now(UTC))) == []


def test_failed_revert_keeps_decision_pending(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    decision = journal.append(KIND_DECISION, _executed_decision_payload())
    revert = journal.append(
        KIND_REVERT, _revert_payload(decision.local_sequence, success=False)
    )
    journal.mark_acked(revert.local_sequence)

    pending = journal.pending_reverts(_expired(datetime.now(UTC)))
    assert [r.local_sequence for r, _ in pending] == [decision.local_sequence]
