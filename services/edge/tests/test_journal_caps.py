"""Journal-as-CapsView suite: only executed, successful containment consumes
the bundle's caps; failed applies bind nothing; reverts and TTL expiry
release active blocks; execute-failure records survive eviction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from services.edge.journal.journal import (
    KIND_DECISION,
    KIND_EXECUTE_FAILED,
    KIND_OBSERVATION,
    KIND_REVERT,
    HashJournal,
)
from services.edge.tests._fixtures import NODE_ID


def make_journal(tmp_path: Path, max_bytes: int = 1 << 20) -> HashJournal:
    return HashJournal(tmp_path, node_id=NODE_ID, boot_id="boot-1", max_bytes=max_bytes)


def executed_payload(
    action_type: str = "block_ip", ttl_seconds: int = 900, success: bool = True
) -> dict[str, Any]:
    """The decision-record shape the daemon's defense loop writes."""
    return {
        "outcome": "execute",
        "rule_string": "edge.c2-egress-active tier=tier2 conf=0.95",
        "reason": "",
        "actor": f"edge:{NODE_ID}@v7",
        "action": {
            "action_type": action_type,
            "executor": "nftables",
            "target": "203.0.113.55",
            "ttl_seconds": ttl_seconds,
        },
        "execution": {
            "success": success,
            "ref": "vigil/edge/test" if success else None,
            "error": None if success else "boom",
        },
    }


def test_failed_execution_consumes_no_cap(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    journal.append(KIND_DECISION, executed_payload(success=False))
    now = datetime.now(UTC)
    assert journal.executed_in_last_hour("block_ip", now) == 0
    assert journal.active_blocks(now) == 0


def test_hour_cap_counts_only_matching_action_type(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    journal.append(KIND_DECISION, executed_payload(action_type="block_ip"))
    journal.append(KIND_DECISION, executed_payload(action_type="block_domain"))
    now = datetime.now(UTC)
    assert journal.executed_in_last_hour("block_ip", now) == 1
    assert journal.executed_in_last_hour("block_domain", now) == 1


def test_hour_cap_window_is_one_hour(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    stale = datetime.now(UTC) - timedelta(hours=2)
    journal.append(KIND_DECISION, executed_payload(), now=stale)
    now = datetime.now(UTC)
    assert journal.executed_in_last_hour("block_ip", now) == 0
    journal.append(KIND_DECISION, executed_payload(), now=now)
    assert journal.executed_in_last_hour("block_ip", now) == 1


def test_active_block_expires_with_ttl(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    now = datetime.now(UTC)
    journal.append(KIND_DECISION, executed_payload(ttl_seconds=900), now=now)
    assert journal.active_blocks(now) == 1
    after = now + timedelta(seconds=901)
    assert journal.active_blocks(after) == 0


def test_successful_revert_releases_block(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    now = datetime.now(UTC)
    decision = journal.append(
        KIND_DECISION, executed_payload(ttl_seconds=3600), now=now
    )
    assert journal.active_blocks(now) == 1
    journal.append(
        KIND_REVERT,
        {
            "revert_of": decision.local_sequence,
            "success": True,
            "ref": "vigil/edge/test",
        },
        now=now,
    )
    assert journal.active_blocks(now) == 0


def test_failed_revert_does_not_release_block(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    now = datetime.now(UTC)
    decision = journal.append(
        KIND_DECISION, executed_payload(ttl_seconds=3600), now=now
    )
    journal.append(
        KIND_REVERT,
        {"revert_of": decision.local_sequence, "success": False, "error": "boom"},
        now=now,
    )
    assert journal.active_blocks(now) == 1


def test_execute_failed_record_survives_overflow(tmp_path: Path) -> None:
    """A failed containment is containment history too — the failure record
    is protected from eviction like a decision."""
    journal = make_journal(tmp_path, max_bytes=1024)
    journal.append(
        KIND_EXECUTE_FAILED,
        {
            "reason": "no_executor_registered",
            "target": "203.0.113.55",
            "padding": "y" * 200,
        },
    )
    for n in range(4):
        journal.append(KIND_OBSERVATION, {"n": n, "padding": "x" * 120})
    failed = [r for r in journal.unacked() if r.kind == KIND_EXECUTE_FAILED]
    assert len(failed) == 1
