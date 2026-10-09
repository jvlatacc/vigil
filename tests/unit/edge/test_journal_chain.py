"""The journal chain: hash serialization, batch verification, legality.

These pin the exact bytes both sides of the mesh hash — a warden and this
control plane must agree to the byte on what a record's hash covers — and
the fail-closed verification order: gaps, breaks, and head disagreements
refuse the batch with the position to resend from; legality is a separate
per-record judgment after the chain holds.
"""

from __future__ import annotations

import pytest

from core.edge.journal import (
    GENESIS_PREV_HASH,
    approval_row_for,
    check_legality,
    record_hash,
    verify_batch,
)

pytestmark = pytest.mark.unit

TS = "2026-10-09T13:00:00Z"


def _record(seq: int, prev_hash: str, **overrides) -> dict:
    record = {
        "seq": seq,
        "ts": TS,
        "mode": "AUTONOMOUS",
        "idempotency_key": f"block_ip:198.51.100.{seq}",
        "action_type": "block_ip",
        "target": "198.51.100.7",
        "decision_rule": "edge-001 met (slm 0.93 >= floor 0.90)",
        "execution": {"status": "executed", "executor": "nftables", "at": TS},
        "prev_hash": prev_hash,
    }
    record.update(overrides)
    return record


def _chain(*seqs: int) -> tuple[list[dict], str]:
    """A chained batch from genesis; returns (records, final head)."""
    records: list[dict] = []
    head = GENESIS_PREV_HASH
    for seq in seqs:
        record = _record(seq, head)
        head = record_hash(head, record)
        records.append(record)
    return records, head


class TestRecordHash:
    def test_is_deterministic(self):
        record = _record(1, GENESIS_PREV_HASH)
        assert record_hash(GENESIS_PREV_HASH, record) == record_hash(
            GENESIS_PREV_HASH, record
        )

    def test_changes_when_the_record_changes(self):
        record = _record(1, GENESIS_PREV_HASH)
        tampered = _record(1, GENESIS_PREV_HASH, target="192.0.2.1")
        assert record_hash(GENESIS_PREV_HASH, record) != record_hash(
            GENESIS_PREV_HASH, tampered
        )

    def test_changes_when_the_previous_hash_changes(self):
        record = _record(1, "a" * 64)
        assert record_hash("a" * 64, record) != record_hash("b" * 64, record)

    def test_prev_hash_is_not_hashed_into_its_own_record(self):
        # record_hash(prev, record) with record["prev_hash"] set to anything
        # must equal the hash without the key at all: the chaining field is
        # the link, not the content.
        record = _record(1, GENESIS_PREV_HASH)
        content = {k: v for k, v in record.items() if k != "prev_hash"}
        assert record_hash(GENESIS_PREV_HASH, record) == record_hash(
            GENESIS_PREV_HASH, content
        )

    def test_hashes_match_the_documented_formula(self):
        import hashlib
        import json

        record = _record(2, "c" * 64)
        content = {k: record[k] for k in record if k != "prev_hash"}
        expected = hashlib.sha256(
            ("c" * 64).encode()
            + json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert record_hash("c" * 64, record) == expected


class TestVerifyBatch:
    def test_first_batch_chains_from_genesis(self):
        records, head = _chain(1, 2, 3)

        verdict = verify_batch(
            records, server_last_seq=0, server_head=None, claimed_head=head
        )

        assert verdict.ok
        assert verdict.accepted_through == 3
        assert verdict.final_head == head
        assert len(verdict.new_records) == 3
        assert not verdict.duplicate_records

    def test_continuation_batch_chains_onto_the_held_head(self):
        first, first_head = _chain(1, 2)
        second, second_head = _chain(3, 4)
        # rebuild second so it chains from the first batch's head
        second = []
        prev = first_head
        for seq in (3, 4):
            record = _record(seq, prev)
            prev = record_hash(prev, record)
            second.append(record)
        _ = second_head

        verdict = verify_batch(
            second, server_last_seq=2, server_head=first_head, claimed_head=prev
        )

        assert verdict.ok
        assert verdict.accepted_through == 4
        assert verdict.final_head == prev

    def test_gap_in_the_middle_refuses_with_resend_position(self):
        first, first_head = _chain(1, 2)
        gapped = [_record(4, first_head)]  # skips seq 3

        verdict = verify_batch(
            gapped, server_last_seq=2, server_head=first_head, claimed_head="x" * 64
        )

        assert not verdict.ok
        assert verdict.code == "seq-gap"
        assert verdict.resend_from == 3
        assert verdict.detail == "expected seq 3, got 4"

    def test_first_record_may_not_skip_ahead(self):
        # A batch that starts past the held head skips unheld records.
        _, head = _chain(1, 2)
        skipped = [_record(5, head)]

        verdict = verify_batch(
            skipped, server_last_seq=2, server_head=head, claimed_head="x" * 64
        )

        assert not verdict.ok
        assert verdict.code == "seq-gap"
        assert verdict.resend_from == 3

    def test_broken_chain_link_refuses(self):
        _, head = _chain(1, 2)
        forged = [_record(3, head), _record(4, "f" * 64)]  # 4 does not chain to 3

        verdict = verify_batch(
            forged, server_last_seq=2, server_head=head, claimed_head="x" * 64
        )

        assert not verdict.ok
        assert verdict.code == "chain-mismatch"

    def test_wrong_claimed_head_refuses(self):
        records, head = _chain(1, 2)

        verdict = verify_batch(
            records, server_last_seq=0, server_head=None, claimed_head="e" * 64
        )

        assert not verdict.ok
        assert verdict.code == "head-mismatch"

    def test_duplicates_are_sorted_out_and_never_block_a_valid_tail(self):
        records, head = _chain(1, 2, 3)

        verdict = verify_batch(
            records,
            server_last_seq=2,
            server_head=record_hash_from_chain(1, 2),
            claimed_head=head,
        )

        assert verdict.ok
        assert [r["seq"] for r in verdict.duplicate_records] == [1, 2]
        assert [r["seq"] for r in verdict.new_records] == [3]
        assert verdict.accepted_through == 3

    def test_all_duplicate_batch_holds_position(self):
        records, head = _chain(1, 2)

        verdict = verify_batch(
            records, server_last_seq=2, server_head=head, claimed_head=head
        )

        assert verdict.ok
        assert verdict.new_records == ()
        assert verdict.accepted_through == 2
        assert verdict.final_head == head

    def test_tampered_duplicate_content_is_ignored_not_merged(self):
        # A re-push of an already-held record with edited content: the
        # duplicate is skipped (its truth is pinned by the next record's
        # prev_hash), and the new tail is verified against the held head.
        records, head = _chain(1, 2)
        held_head = records[0] and record_hash_from_chain(1)
        forged_dup = _record(1, GENESIS_PREV_HASH, target="203.0.113.9")
        batch = [forged_dup, records[1]]

        verdict = verify_batch(
            batch, server_last_seq=1, server_head=held_head, claimed_head=head
        )

        assert verdict.ok
        assert [r["seq"] for r in verdict.duplicate_records] == [1]
        assert [r["seq"] for r in verdict.new_records] == [2]
        # and the forged content never enters the verdict's new records
        assert all(r["target"] != "203.0.113.9" for r in verdict.new_records)

    def test_descending_seq_refuses(self):
        _, head = _chain(1, 2, 3)
        descending = [_record(5, head), _record(4, "f" * 64)]

        verdict = verify_batch(
            descending, server_last_seq=3, server_head=head, claimed_head="x" * 64
        )

        assert not verdict.ok
        assert verdict.code == "seq-gap"

    def test_empty_batch_refuses(self):
        verdict = verify_batch(
            [], server_last_seq=0, server_head=None, claimed_head="x" * 64
        )

        assert not verdict.ok
        assert verdict.code == "empty-batch"

    def test_non_integer_seq_refuses(self):
        bad = [_record("1", GENESIS_PREV_HASH)]

        verdict = verify_batch(
            bad, server_last_seq=0, server_head=None, claimed_head="x" * 64
        )

        assert not verdict.ok
        assert verdict.code == "seq-order"


def record_hash_from_chain(*seqs: int) -> str:
    """The head after chaining records 1..N built by _chain's helper."""
    head = GENESIS_PREV_HASH
    for seq in seqs:
        head = record_hash(head, _record(seq, head))
    return head


class TestCheckLegality:
    def test_unknown_cited_version_rejects_every_record(self):
        records, _ = _chain(1, 2)

        verdict = check_legality(records, allowed_actions=None)

        assert verdict.accepted == ()
        assert [r.seq for r in verdict.rejected] == [1, 2]
        assert all(r.code == "policy-version-unavailable" for r in verdict.rejected)

    def test_action_inside_the_envelope_is_accepted(self):
        records, _ = _chain(1)

        verdict = check_legality(records, allowed_actions=("block_ip",))

        assert [r["seq"] for r in verdict.accepted] == [1]
        assert verdict.rejected == ()

    def test_action_outside_the_envelope_is_rejected(self):
        forged = [_record(1, GENESIS_PREV_HASH, action_type="process_kill")]

        verdict = check_legality(forged, allowed_actions=("block_ip",))

        assert verdict.accepted == ()
        assert verdict.rejected[0].code == "action-not-in-envelope"
        assert "process_kill" in verdict.rejected[0].detail

    def test_mixed_batch_splits_cleanly(self):
        batch = [
            _record(1, GENESIS_PREV_HASH, action_type="block_ip"),
            _record(2, "a" * 64, action_type="disable_user"),
        ]

        verdict = check_legality(batch, allowed_actions=("block_ip", "unblock_ip"))

        assert [r["seq"] for r in verdict.accepted] == [1]
        assert [r.seq for r in verdict.rejected] == [2]


class TestApprovalRowMapping:
    def test_executed_record_maps_to_the_approval_vocabulary(self):
        record = _record(7, GENESIS_PREV_HASH)

        row = approval_row_for(record, node_id="wn-7f3a", policy_version=42)

        assert row["action_id"] == "edge-wn-7f3a-000000000007"
        assert row["action_type"] == "block_ip"
        assert row["target"] == "198.51.100.7"
        assert row["status"] == "executed"
        assert row["requires_approval"] is False
        assert row["executed_at"] == TS
        assert row["reversibility"] == "reversible"
        assert row["idempotency_key"] == "block_ip:198.51.100.7"
        # provenance: these rows are machine-decided by signed policy
        assert row["parameters"]["source"] == "edge"
        assert row["parameters"]["node_id"] == "wn-7f3a"
        assert row["parameters"]["policy_version"] == 42
        assert row["parameters"]["seq"] == 7
        assert row["parameters"]["mode"] == "AUTONOMOUS"
        assert row["execution_result"] == record["execution"]

    def test_failed_record_maps_to_failed(self):
        record = _record(
            1,
            GENESIS_PREV_HASH,
            execution={"status": "failed", "executor": "nftables", "at": TS},
        )

        row = approval_row_for(record, node_id="wn-7f3a", policy_version=42)

        assert row["status"] == "failed"
        assert row["requires_approval"] is False
        assert row["executed_at"] is None

    def test_dry_run_is_pending_and_needs_a_person(self):
        # The _execute_isolation lesson: a success must never be recorded for
        # containment that never happened. A dry run surfaces as pending work.
        record = _record(
            1, GENESIS_PREV_HASH, execution={"status": "dry_run", "executor": "dry-run"}
        )

        row = approval_row_for(record, node_id="wn-7f3a", policy_version=42)

        assert row["status"] == "pending"
        assert row["requires_approval"] is True
        assert row["executed_at"] is None

    def test_action_id_fits_the_column_for_long_node_ids(self):
        record = _record(999999999999, GENESIS_PREV_HASH)

        row = approval_row_for(record, node_id="w" * 50, policy_version=1)

        assert len(row["action_id"]) <= 80
