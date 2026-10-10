"""The hash-chained journal: tamper detection, torn tails, appends."""

import json
import stat
from pathlib import Path

import pytest

from core.edge.journal import GENESIS_PREV_HASH, record_hash
from services.warden.journal import Journal, JournalPoisonedError


def record_kwargs(seq: int = 1, target: str = "198.51.100.7") -> dict:
    return {
        "mode": "AUTONOMOUS",
        "idempotency_key": f"block_ip:{target}",
        "action_type": "block_ip",
        "target": target,
        "decision_rule": f"edge-001 met (record {seq})",
        "execution": {"status": "executed", "executor": "dry_run"},
        "ts": f"2026-10-10T12:00:0{seq % 10}Z",
    }


def write_lines(path: Path, *lines: str) -> None:
    path.write_text("".join(line + "\n" for line in lines))


class TestAppendAndChain:
    def test_first_record_chains_from_genesis(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "journal.jsonl")
        record = journal.append(**record_kwargs())
        assert record["seq"] == 1
        assert record["prev_hash"] == GENESIS_PREV_HASH

    def test_records_chain_via_record_hash(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "journal.jsonl")
        first = journal.append(**record_kwargs(target="198.51.100.7"))
        second = journal.append(**record_kwargs(target="198.51.100.8"))
        first_hash = record_hash(first["prev_hash"], first)
        assert second["prev_hash"] == first_hash

    def test_head_tracks_seq_and_hash(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "journal.jsonl")
        assert journal.status().head_seq == 0
        assert journal.status().head_hash is None
        journal.append(**record_kwargs())
        journal.append(**record_kwargs(target="198.51.100.8"))
        status = journal.status()
        assert status.head_seq == 2
        assert status.head_hash is not None
        assert not status.poisoned

    def test_file_and_directory_permissions(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        Journal(path)
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        journal = Journal(path)
        journal.append(**record_kwargs())
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_reload_sees_appended_records(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        journal = Journal(path)
        journal.append(**record_kwargs())
        journal.append(**record_kwargs(target="198.51.100.8"))
        reloaded = Journal(path)
        assert reloaded.status().head_seq == 2
        assert len(reloaded.records_after(0)) == 2


class TestTamperDetection:
    def test_edited_middle_record_poisons_the_journal(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        journal = Journal(path)
        journal.append(**record_kwargs(target="198.51.100.7"))
        journal.append(**record_kwargs(target="198.51.100.8"))
        journal.append(**record_kwargs(target="198.51.100.9"))

        lines = path.read_text().splitlines()
        tampered = json.loads(lines[1])
        tampered["target"] = "203.0.113.1"  # attacker rewrote history
        lines[1] = json.dumps(tampered, separators=(",", ":"))
        write_lines(path, *lines)

        reloaded = Journal(path)
        assert reloaded.status().poisoned
        assert "chain" in reloaded.status().reason or "seq" in reloaded.status().reason
        with pytest.raises(JournalPoisonedError):
            reloaded.append(**record_kwargs())

    def test_deleted_record_is_a_gap(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        journal = Journal(path)
        journal.append(**record_kwargs())
        journal.append(**record_kwargs(target="198.51.100.8"))
        journal.append(**record_kwargs(target="198.51.100.9"))

        lines = path.read_text().splitlines()
        del lines[1]  # seq 1, 3: a gap the server would 409
        write_lines(path, *lines)

        reloaded = Journal(path)
        assert reloaded.status().poisoned
        assert "seq" in reloaded.status().reason

    def test_garbage_middle_line_poisons(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        journal = Journal(path)
        journal.append(**record_kwargs())
        with open(path, "a") as handle:
            handle.write("{{{not json at all\n")
        journal.append(**record_kwargs(target="198.51.100.8"))

        reloaded = Journal(path)
        assert reloaded.status().poisoned

    def test_extra_field_on_a_record_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        journal = Journal(path)
        record = journal.append(**record_kwargs())
        lines = path.read_text().splitlines()
        widened = dict(record)
        widened["attacker_field"] = "ignored-by-hash-anyway"
        lines[0] = json.dumps(widened, separators=(",", ":"))
        # A widened record changes the line but the hash chain covers only
        # RECORD_FIELDS; the loader must still refuse unknown shapes.
        write_lines(path, *lines)
        reloaded = Journal(path)
        assert reloaded.status().poisoned


class TestTornTail:
    def test_torn_final_line_is_quarantined(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        journal = Journal(path)
        journal.append(**record_kwargs())
        with open(path, "a") as handle:  # a crash mid-write
            handle.write('{"seq": 2, "ts": "2026-10-10T12:0')

        torn = path.with_suffix(".jsonl.torn")
        reloaded = Journal(path)
        assert not reloaded.status().poisoned
        assert reloaded.status().head_seq == 1
        assert torn.exists()  # kept for forensics
        assert '"seq": 2' in torn.read_text()  # the torn bytes, moved aside

    def test_chain_continues_after_quarantine(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        journal = Journal(path)
        journal.append(**record_kwargs())
        with open(path, "a") as handle:
            handle.write('{"seq": 2, "mo')

        reloaded = Journal(path)
        assert not reloaded.status().poisoned
        second = reloaded.append(**record_kwargs(target="198.51.100.8"))
        assert second["seq"] == 2  # sequence resumes after the intact prefix

        final = Journal(path)  # and the chain still verifies from disk
        assert final.status().head_seq == 2
        assert not final.status().poisoned
