"""Journal suite: hash-chain construction and tamper detection, the
node_id+boot_id+local_sequence idempotency key, durable-ack compaction,
and bounded eviction with explicit loss counters — never silent discard."""

from __future__ import annotations

import json
from pathlib import Path

from services.edge.journal.journal import (
    GENESIS_HASH,
    KIND_DECISION,
    KIND_OBSERVATION,
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
